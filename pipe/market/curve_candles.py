from __future__ import annotations

"""OHLCV for a live launch curve before a DEX pool is indexed.

The public Solana RPC exposes the curve's transaction signatures and confirmed
transaction logs. Pump's published IDL defines the TradeEvent prefix emitted
by every successful curve trade. Reading that prefix gives us the post-trade
virtual reserves, execution size and timestamp, which is enough to build real
candles without inventing history or depending on an undocumented REST feed.
"""

import base64
import math
import struct
import time
from dataclasses import dataclass, field
from typing import Any

from pipe import db
from pipe.chain.rpc import RpcClient, RpcError
from pipe.market.candles import CandlesUnavailable, TIMEFRAMES


TRADE_EVENT_DISCRIMINATOR = bytes([189, 219, 127, 211, 78, 230, 97, 238])
RAW_FRAME = "curve-1m"
FETCH_TTL = 15.0
SIGNATURE_LIMIT = 250
TRANSACTION_LIMIT = 64

_memory: dict[str, tuple[float, list[dict]]] = {}


@dataclass
class CurveSeries:
    mint: str
    pool: str
    dex: str = ""
    timeframe: str = "1m"
    bars: list[dict] = field(default_factory=list)
    fetched_at: float = 0.0
    stale: bool = False
    source: str = "on-chain curve"


def _trade_from_logs(logs: list[str], decimals: int, sol_usd: float) -> dict | None:
    """Decode the stable TradeEvent prefix from one confirmed transaction."""
    for entry in logs or []:
        if not isinstance(entry, str) or not entry.startswith("Program data: "):
            continue
        try:
            raw = base64.b64decode(entry.split(": ", 1)[1], validate=True)
        except (ValueError, TypeError):
            continue
        if len(raw) < 113 or raw[:8] != TRADE_EVENT_DISCRIMINATOR:
            continue

        sol_amount = struct.unpack_from("<Q", raw, 40)[0]
        token_amount = struct.unpack_from("<Q", raw, 48)[0]
        timestamp = struct.unpack_from("<q", raw, 89)[0]
        virtual_sol = struct.unpack_from("<Q", raw, 97)[0]
        virtual_token = struct.unpack_from("<Q", raw, 105)[0]

        token_scale = 10 ** max(0, min(int(decimals), 18))
        if virtual_sol and virtual_token:
            price_sol = (virtual_sol / 1_000_000_000) / (virtual_token / token_scale)
        elif sol_amount and token_amount:
            price_sol = (sol_amount / 1_000_000_000) / (token_amount / token_scale)
        else:
            continue
        price = price_sol * sol_usd
        volume = (sol_amount / 1_000_000_000) * sol_usd
        if timestamp <= 0 or not math.isfinite(price) or price <= 0:
            continue
        return {"t": int(timestamp), "price": price, "volume": max(0.0, volume)}
    return None


def _one_minute(points: list[dict]) -> list[dict]:
    bars: list[dict] = []
    for point in sorted(points, key=lambda item: item["t"]):
        stamp = point["t"] - (point["t"] % 60)
        price = point["price"]
        if bars and bars[-1]["t"] == stamp:
            bar = bars[-1]
            bar["h"] = max(bar["h"], price)
            bar["l"] = min(bar["l"], price)
            bar["c"] = price
            bar["v"] += point["volume"]
        else:
            bars.append({"t": stamp, "o": price, "h": price, "l": price, "c": price, "v": point["volume"]})
    return bars


def _roll(bars: list[dict], seconds: int) -> list[dict]:
    out: list[dict] = []
    for source in bars:
        stamp = source["t"] - (source["t"] % seconds)
        if out and out[-1]["t"] == stamp:
            bar = out[-1]
            bar["h"] = max(bar["h"], source["h"])
            bar["l"] = min(bar["l"], source["l"])
            bar["c"] = source["c"]
            bar["v"] += source["v"]
        else:
            out.append({"t": stamp, "o": source["o"], "h": source["h"], "l": source["l"], "c": source["c"], "v": source["v"]})
    return out


def _merge(old: list[dict], new: list[dict]) -> list[dict]:
    by_time = {int(bar["t"]): bar for bar in old}
    by_time.update({int(bar["t"]): bar for bar in new})
    return [by_time[key] for key in sorted(by_time)]


def _fetch(mint: str, curve: str, decimals: int, sol_usd: float) -> list[dict]:
    rpc = RpcClient(timeout=28, retries=1)
    signatures = rpc.call(
        "getSignaturesForAddress",
        [curve, {"limit": SIGNATURE_LIMIT, "commitment": "confirmed"}],
    ) or []
    successful = [item.get("signature") for item in signatures if not item.get("err") and item.get("signature")]
    successful = successful[:TRANSACTION_LIMIT]
    if not successful:
        return []

    calls = [
        (
            "getTransaction",
            [signature, {"encoding": "base64", "commitment": "confirmed", "maxSupportedTransactionVersion": 0}],
        )
        for signature in successful
    ]
    transactions = rpc.batch(calls)
    points: list[dict] = []
    for transaction in transactions:
        logs = ((transaction or {}).get("meta") or {}).get("logMessages") or []
        point = _trade_from_logs(logs, decimals, sol_usd)
        if point:
            points.append(point)
    return _one_minute(points)


def series(
    mint: str,
    *,
    curve: str,
    decimals: int,
    sol_usd: float,
    timeframe: str = "5m",
    limit: int = 300,
) -> CurveSeries:
    if timeframe not in TIMEFRAMES:
        timeframe = "5m"
    storage_key = f"curve:{mint}"
    now = time.time()
    hit = _memory.get(mint)
    bars = hit[1] if hit else []
    age = now - hit[0] if hit else None

    if db.configured():
        try:
            stored = db.read_candles(storage_key, RAW_FRAME, 1000)
            bars = _merge(stored, bars)
            stored_age = db.candle_age(storage_key, RAW_FRAME)
            age = stored_age if stored_age is not None else age
        except Exception:
            pass

    should_fetch = age is None or age >= FETCH_TTL
    if should_fetch and db.configured():
        try:
            should_fetch = db.claim_candle_fetch(storage_key, RAW_FRAME, FETCH_TTL)
        except Exception:
            should_fetch = True

    fetched = False
    if should_fetch:
        try:
            fresh = _fetch(mint, curve, decimals, sol_usd)
        except RpcError as exc:
            if not bars:
                raise CandlesUnavailable(f"The chain could not return recent curve trades: {exc}") from exc
            fresh = []
        if fresh:
            bars = _merge(bars, fresh)
            fetched = True
            if db.configured():
                try:
                    db.save_candles(storage_key, RAW_FRAME, fresh)
                except Exception:
                    pass
        _memory[mint] = (now, bars)

    if not bars:
        raise CandlesUnavailable("Waiting for the first confirmed curve trade. The chart will appear automatically.")

    seconds = TIMEFRAMES[timeframe][2]
    shown = bars if seconds == 60 else _roll(bars, seconds)
    taken = now if fetched else now - (age or 0.0)
    return CurveSeries(
        mint=mint,
        pool=storage_key,
        timeframe=timeframe,
        bars=shown[-limit:],
        fetched_at=taken,
        stale=bool(age is not None and age > FETCH_TTL * 3 and not fetched),
    )
