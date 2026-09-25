from __future__ import annotations

"""
Routes.

The feed is assembled from three sources, each doing the one thing it is best
at:

  pump.fun      that a coin exists at all, its creator, and how far along the
                bonding curve it is — the only place `complete` comes from
  the mint      whether the supply can grow and whether balances can be
                frozen, read straight off the mint account without a key
  DexScreener   price, liquidity, volume and a better image, once anything has
                indexed a market

Holders are deliberately absent from the feed. The call that reads them is the
one no free endpoint will serve, so it happens on the token page and only when
a keyed endpoint is configured.
"""

import json
import time
from dataclasses import asdict
from typing import Any

from pipe import db
from pipe.analysis import read as reader
from pipe.chain import pumpfun
from pipe.chain.holders import distribution
from pipe.chain.rpc import RpcClient, RpcError, RpcUnavailable
from pipe.chain.spl import mint_info_many
from pipe.config import DEXSCREENER_CHAIN, LAMPORTS, WSOL_MINT, holders_available
from pipe.market import jupiter
from pipe.market.candles import TIMEFRAMES, CandlesUnavailable, series
from pipe.market.dexscreener import markets_for

_CACHE: dict[str, tuple[float, Any]] = {}


def cached(key: str, seconds: float, build):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < seconds:
        return hit[1]
    value = build()
    _CACHE[key] = (now, value)
    return value


def envelope(ok: bool, data: Any = None, error: str = "") -> dict:
    return {"ok": ok, "data": data, "error": error or None}


def _row(coin, mint_info, market) -> dict:
    info = mint_info.get(coin.mint)
    m = market.get(coin.mint)
    return {
        "mint": coin.mint,
        "symbol": coin.symbol or "?",
        "name": coin.name or "",
        "creator": coin.creator,
        "created_ms": coin.created_ms,
        "age_minutes": coin.age_minutes,
        "complete": coin.complete,
        "progress": round(coin.progress, 4),
        "stage": coin.stage,
        "bonding_curve": coin.bonding_curve,
        "pool_address": coin.pool_address,
        "reply_count": coin.reply_count,
        "decimals": info.decimals if info else coin.decimals,
        # authorities — the two facts that decide whether a mint can be used
        # against whoever holds it
        "mint_readable": bool(info.readable) if info else False,
        "can_inflate": bool(info.can_inflate) if info else False,
        "can_freeze": bool(info.can_freeze) if info else False,
        # market, when anything has indexed one
        "indexed": bool(m),
        "image_url": (m.image_url if m and m.image_url else coin.image_uri) or "",
        "price_usd": m.price_usd if m else 0.0,
        "liquidity_usd": m.liquidity_usd if m else 0.0,
        "fdv": (m.fdv or m.market_cap) if m else coin.market_cap_usd,
        "volume_h1": m.volume_h1 if m else 0.0,
        "volume_h24": m.volume_h24 if m else 0.0,
        "buys_h1": m.buys_h1 if m else 0,
        "sells_h1": m.sells_h1 if m else 0,
        "change_m5": m.change_m5 if m else 0.0,
        "change_h1": m.change_h1 if m else 0.0,
        "change_h24": m.change_h24 if m else 0.0,
        "quote_symbol": (m.quote_symbol if m else "") or "SOL",
    }


def _enrich(coins: list) -> list[dict]:
    if not coins:
        return []
    mints = [coin.mint for coin in coins]
    try:
        info = mint_info_many(RpcClient(), mints)
    except RpcError:
        # The public endpoint rate limits. Losing the authority checks is
        # worth saying, not worth dropping the whole page for.
        info = {}
    market = markets_for(mints)
    rows = [_row(coin, info, market) for coin in coins]
    for row in rows:
        row["risk"] = reader.risk_only(row)
    return rows


def feed_route(query: dict) -> dict:
    limit = min(int(query.get("limit", ["40"])[0] or 40), 80)

    def build():
        fresh = pumpfun.newest(limit)
        stretch = pumpfun.about_to_graduate(min(limit, 30))
        done = pumpfun.migrated(min(limit, 30))

        seen: dict[str, Any] = {}
        for group in (fresh, stretch, done):
            for coin in group:
                seen.setdefault(coin.mint, coin)

        rows = {row["mint"]: row for row in _enrich(list(seen.values()))}
        return {
            "chain": "solana",
            "source": "live",
            "holders_available": holders_available(),
            "columns": {
                "new": [rows[c.mint] for c in fresh if c.mint in rows],
                "stretch": [rows[c.mint] for c in stretch if c.mint in rows],
                "migrated": [rows[c.mint] for c in done if c.mint in rows],
            },
        }

    return envelope(True, cached(f"feed:{limit}", 8.0, build))


def token_route(mint: str) -> dict:
    def build():
        coin = pumpfun.one(mint)
        if not coin:
            return None
        rows = _enrich([coin])
        if not rows:
            return None
        row = rows[0]
        return {"token": row, "holders": None, "read": reader.build(row, None)}

    data = cached(f"token:{mint}", 10.0, build)
    if not data:
        return envelope(False, error="Coin not found on pump.fun.")
    return envelope(True, data)


def holders_route(mint: str) -> dict:
    if not holders_available():
        return envelope(
            False,
            error=(
                "Holder data needs a keyed RPC. No free Solana endpoint serves "
                "getTokenLargestAccounts — mainnet-beta answers 429, ankr and publicnode 403. "
                "Set HELIUS_API_KEY or SOLANA_RPC_URL and this fills in."
            ),
        )

    def build():
        coin = pumpfun.one(mint)
        if not coin:
            return None
        dist = distribution(
            RpcClient(),
            mint=mint,
            creator=coin.creator,
            curve=coin.bonding_curve,
            pool=coin.pool_address,
        )
        return {
            "mint": mint,
            "counted": dist.counted,
            "top10_share": dist.top10_share,
            "creator_share": dist.creator_share,
            "curve_share": dist.curve_share,
            "truncated": dist.truncated,
            "note": dist.note,
            "holders": [asdict(h) for h in dist.holders],
        }

    try:
        data = cached(f"holders:{mint}", 25.0, build)
    except RpcUnavailable as exc:
        return envelope(False, error=str(exc))
    except RpcError as exc:
        return envelope(False, error=f"The RPC refused the holder call: {exc}")
    if not data:
        return envelope(False, error="Coin not found.")
    return envelope(True, data)


def candles_route(mint: str, query: dict) -> dict:
    """
    OHLCV for the deepest pool that has indexed the coin. A refusal comes back
    as a refusal — an empty chart and a flat line are the same picture, and one
    of them is a lie.
    """
    timeframe = (query.get("tf", ["5m"])[0] or "5m").strip()
    pool = (query.get("pool", [""])[0] or "").strip()
    if not pool:
        # DexScreener already knows the deepest pair and answers generously.
        # GeckoTerminal does not, so its budget goes entirely on the candles.
        found = cached(f"pair:{mint}", 120.0, lambda: markets_for([mint]).get(mint))
        pool = getattr(found, "pair_address", "") or ""
        known_dex = getattr(found, "dex", "") or ""
    else:
        known_dex = ""
    try:
        limit = max(30, min(int(query.get("limit", ["300"])[0]), 1000))
    except (TypeError, ValueError):
        limit = 300
    try:
        data = series(mint, timeframe=timeframe, limit=limit, pool=pool)
    except CandlesUnavailable as exc:
        return envelope(False, error=str(exc))
    return envelope(
        True,
        {
            "mint": mint,
            "pool": data.pool,
            "dex": data.dex or known_dex,
            "timeframe": data.timeframe,
            "timeframes": list(TIMEFRAMES),
            "stale": data.stale,
            "fetched_at": data.fetched_at,
            "bars": data.bars,
        },
    )


def wallet_route(owner: str, query: dict) -> dict:
    """What the connected wallet can actually spend, before it is offered a trade."""
    mint = (query.get("mint", [""])[0] or "").strip()

    def build():
        client = RpcClient()
        out = {"owner": owner, "lamports": client.sol_balance(owner), "sol": 0.0}
        out["sol"] = out["lamports"] / LAMPORTS
        if mint and mint != WSOL_MINT:
            held = client.token_balance(owner, mint)
            out["token"] = held
            out["token_ui"] = held["amount"] / (10 ** held["decimals"]) if held["decimals"] else 0.0
        return out

    try:
        return envelope(True, cached(f"wallet:{owner}:{mint}", 8.0, build))
    except RpcError as exc:
        return envelope(False, error=f"The RPC would not read that wallet: {exc}")


def quote_route(body: dict) -> tuple[int, dict]:
    side = (body.get("side") or "buy").lower()
    mint = (body.get("mint") or "").strip()
    if not mint:
        return 400, envelope(False, error="No mint.")
    try:
        amount = int(body.get("amount") or 0)
    except (TypeError, ValueError):
        return 400, envelope(False, error="Amount must be a whole number of base units.")
    slippage = int(body.get("slippage_bps") or 150)
    input_mint, output_mint = (WSOL_MINT, mint) if side == "buy" else (mint, WSOL_MINT)
    try:
        q = jupiter.quote(input_mint, output_mint, amount, slippage)
    except jupiter.JupiterError as exc:
        return 200, envelope(False, error=str(exc))
    return 200, envelope(
        True,
        {
            "side": side,
            "input_mint": q.input_mint,
            "output_mint": q.output_mint,
            "in_amount": q.in_amount,
            "out_amount": q.out_amount,
            "min_out_amount": q.min_out_amount,
            "price_impact_pct": q.price_impact_pct,
            "slippage_bps": q.slippage_bps,
            "route": q.route,
            "quote": q.raw,
        },
    )


def swap_route(body: dict) -> tuple[int, dict]:
    """
    Builds the transaction and hands it back unsigned. The wallet in the
    reader's browser is the only thing that signs it and the only thing that
    sends it; nothing on this side can.
    """
    owner = (body.get("owner") or "").strip()
    raw = body.get("quote")
    if not owner or not isinstance(raw, dict):
        return 400, envelope(False, error="A swap needs a wallet address and the quote it was priced from.")
    try:
        priority = int(body.get("priority_lamports") or 1_000_000)
    except (TypeError, ValueError):
        priority = 1_000_000
    try:
        return 200, envelope(True, jupiter.swap_transaction(raw, owner, priority))
    except jupiter.JupiterError as exc:
        return 200, envelope(False, error=str(exc))


def tx_route(signature: str) -> dict:
    """
    Whether the swap landed. The wallet returns a signature the instant it
    sends, which is not the same as the trade having happened, and a panel
    that stops at "sent" is telling the reader something it does not know.
    """
    def build():
        client = RpcClient()
        out = client.call("getSignatureStatuses", [[signature], {"searchTransactionHistory": True}])
        value = ((out or {}).get("value") or [None])[0]
        if not value:
            return {"signature": signature, "status": "pending", "confirmations": None, "error": None}
        return {
            "signature": signature,
            "status": "failed" if value.get("err") else (value.get("confirmationStatus") or "processed"),
            "confirmations": value.get("confirmations"),
            "slot": value.get("slot"),
            "error": json.dumps(value.get("err")) if value.get("err") else None,
        }

    try:
        return envelope(True, cached(f"tx:{signature}", 2.0, build))
    except RpcError as exc:
        return envelope(False, error=f"Could not read the transaction status: {exc}")


def health_route() -> dict:
    out: dict[str, Any] = {
        "chain": "solana",
        "dexscreener": DEXSCREENER_CHAIN,
        "holders": "available" if holders_available() else "needs a keyed rpc",
        "database": "configured" if db.configured() else "absent",
    }
    if db.configured():
        # Worth surfacing: without a shared candle store the chart falls back
        # to per-instance memory, and on a serverless host that means it will
        # say "stale" often. This number is how you tell it is working.
        try:
            out["stored"] = db.stats()
        except Exception as exc:
            # A fresh database has the credentials but not the tables, which is
            # a different problem from one that cannot be reached and has a
            # different fix: run the indexer once.
            missing = "does not exist" in str(exc)
            out["database"] = (
                "configured, not migrated — POST /api/index once to create the schema"
                if missing
                else f"configured but unreachable: {exc}"
            )
    client = RpcClient()
    try:
        out["slot"] = client.slot()
        out["rpc"] = "ok"
    except RpcError as exc:
        out["rpc"] = f"unreachable: {exc}"
    out["launches"] = "ok" if pumpfun.newest(1) else "unreachable"
    return envelope(True, out)


def handle_get(path: str, query: dict) -> tuple[int, dict] | None:
    if path == "/api/health":
        return 200, health_route()
    if path == "/api/feed":
        return 200, feed_route(query)
    if path.startswith("/api/tx/"):
        signature = path[len("/api/tx/"):].strip("/")
        if signature:
            payload = tx_route(signature)
            return (200 if payload["ok"] else 409), payload
    if path.startswith("/api/wallet/"):
        owner = path[len("/api/wallet/"):].strip("/")
        if owner:
            payload = wallet_route(owner, query)
            return (200 if payload["ok"] else 409), payload
    if path.startswith("/api/token/"):
        rest = path[len("/api/token/"):].strip("/")
        if rest.endswith("/candles"):
            payload = candles_route(rest[: -len("/candles")], query)
            return (200 if payload["ok"] else 409), payload
        if rest.endswith("/holders"):
            payload = holders_route(rest[: -len("/holders")])
            return (200 if payload["ok"] else 409), payload
        if rest:
            payload = token_route(rest)
            return (200 if payload["ok"] else 404), payload
    return None


def handle_post(path: str, secret_ok: bool, body: dict | None = None) -> tuple[int, dict] | None:
    if path == "/api/quote":
        return quote_route(body or {})
    if path == "/api/swap":
        return swap_route(body or {})
    if path == "/api/index":
        if not secret_ok:
            return 401, envelope(False, error="Missing or wrong CRON_SECRET.")
        from pipe.indexer import run_all

        try:
            return 200, envelope(True, run_all())
        except Exception as exc:
            return 500, envelope(False, error=str(exc))
    return None
