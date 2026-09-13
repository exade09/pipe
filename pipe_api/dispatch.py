from __future__ import annotations

"""
Routes.

Two modes, chosen by whether DATABASE_URL is set:

  with a database  — reads the indexed feed, which has history and filters
  without one      — reads a short window straight off the chain

The second mode is not a stub. It is what runs on a fresh deploy before the
first cron fires, and it says so in the payload so the UI can tell the user
the window is small rather than showing an empty feed and looking broken.
"""

import json
import time
from dataclasses import asdict
from typing import Any

from pipe import db
from pipe.analysis import read as reader
from pipe.chain.erc20 import metadata_many
from pipe.chain.holders import distribution
from pipe.chain.pons import recent_launches
from pipe.chain.rpc import RpcClient, RpcError
from pipe.config import CHAIN_ID, ZERO_ADDRESS, blocks_for_minutes
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


def _age_minutes(launch_block: int, head: int) -> int:
    return max(0, int((head - launch_block) * 0.1 / 60))


def _row_from_chain(launch, meta, market, head) -> dict:
    token = launch.token
    m = market.get(token)
    info = meta.get(token)
    return {
        "address": token,
        "curve": launch.curve,
        "deployer": launch.deployer,
        "pair_token": launch.pair_token,
        "native_pair": launch.native_pair,
        "launch_block": launch.block,
        "age_minutes": _age_minutes(launch.block, head),
        "symbol": (info.symbol if info else "") or "?",
        "name": (info.name if info else "") or "",
        "decimals": info.decimals if info else 18,
        "image_url": m.image_url if m else "",
        "price_usd": m.price_usd if m else 0.0,
        "liquidity_usd": m.liquidity_usd if m else 0.0,
        "fdv": (m.fdv or m.market_cap) if m else 0.0,
        "volume_h1": m.volume_h1 if m else 0.0,
        "volume_h24": m.volume_h24 if m else 0.0,
        "buys_h1": m.buys_h1 if m else 0,
        "sells_h1": m.sells_h1 if m else 0,
        "change_m5": m.change_m5 if m else 0.0,
        "change_h1": m.change_h1 if m else 0.0,
        "change_h24": m.change_h24 if m else 0.0,
        "quote_symbol": (m.quote_symbol if m else "") or "ETH",
        "indexed": bool(m),
    }


def feed_route(query: dict) -> dict:
    limit = min(int(query.get("limit", ["60"])[0] or 60), 120)
    order = (query.get("order", ["new"])[0] or "new").lower()
    min_liq = float(query.get("min_liquidity", ["0"])[0] or 0)

    if db.configured():
        rows = db.feed(limit=limit, order=order, min_liquidity=min_liq)
        client = RpcClient()
        head = cached("head", 2.0, client.block_number)
        for row in rows:
            row["age_minutes"] = _age_minutes(int(row["launch_block"]), head)
            row["native_pair"] = row.get("pair_token", "") in ("", ZERO_ADDRESS)
            row["indexed"] = row.get("liquidity_usd", 0) > 0
            row["total_supply"] = str(row.get("total_supply", 0))
            row["first_seen"] = str(row.get("first_seen", ""))
            row["risk"] = reader.risk_only(row)
        return envelope(True, {"source": "index", "head": head, "chain_id": CHAIN_ID, "rows": rows})

    def build():
        client = RpcClient()
        head = client.block_number()
        # The no-database path reads the chain on every request, so it asks for
        # less than the indexed path does. Thirty tokens is under three metadata
        # batches; ninety was enough to earn a 429 and an empty feed.
        launches = recent_launches(client, blocks=blocks_for_minutes(12))[: min(limit, 30)]
        addresses = [item.token for item in launches]
        meta = metadata_many(client, addresses) if addresses else {}
        market = markets_for(addresses) if addresses else {}
        rows = [_row_from_chain(item, meta, market, head) for item in launches]
        for row in rows:
            row["risk"] = reader.risk_only(row)
        if min_liq:
            rows = [r for r in rows if r["liquidity_usd"] >= min_liq]
        return {
            "source": "chain",
            "window_minutes": 12,
            "head": head,
            "chain_id": CHAIN_ID,
            "rows": rows,
            "note": "No DATABASE_URL set, so this is a live twelve-minute window rather than the indexed feed.",
        }

    return envelope(True, cached(f"feed:{limit}:{min_liq}", 6.0, build))


def token_route(address: str) -> dict:
    address = address.lower()
    if db.configured():
        row = db.token(address)
        if row:
            client = RpcClient()
            head = cached("head", 2.0, client.block_number)
            row["age_minutes"] = _age_minutes(int(row["launch_block"]), head)
            row["total_supply"] = str(row.get("total_supply", 0))
            row["first_seen"] = str(row.get("first_seen", ""))
            snapshot = db.holders(address)
            if snapshot:
                snapshot["clusters"] = snapshot.get("clusters") or []
                snapshot["holders"] = snapshot.get("holders") or []
                snapshot["taken_at"] = str(snapshot.get("taken_at", ""))
            row["risk"] = reader.risk_only(row)
            return envelope(True, {"token": row, "holders": snapshot, "read": reader.build(row, snapshot)})

    def build():
        client = RpcClient()
        head = client.block_number()
        launches = recent_launches(client, blocks=blocks_for_minutes(90))
        found = next((item for item in launches if item.token == address), None)
        if not found:
            return None
        meta = metadata_many(client, [address])
        market = markets_for([address])
        row = _row_from_chain(found, meta, market, head)
        row["risk"] = reader.risk_only(row)
        return {"token": row, "holders": None, "read": reader.build(row, None)}

    data = cached(f"token:{address}", 8.0, build)
    if not data:
        return envelope(False, error="Token not found in the recent window.")
    return envelope(True, data)


def holders_route(address: str) -> dict:
    address = address.lower()

    def build():
        client = RpcClient()
        head = client.block_number()
        if db.configured():
            row = db.token(address)
            if not row:
                return None
            curve, deployer, start = row["curve"], row["deployer"], int(row["launch_block"])
        else:
            launches = recent_launches(client, blocks=blocks_for_minutes(90))
            found = next((item for item in launches if item.token == address), None)
            if not found:
                return None
            curve, deployer, start = found.curve, found.deployer, found.block
        dist = distribution(
            client, token=address, curve=curve, deployer=deployer,
            from_block=start, to_block=head, limit=60,
        )
        return {
            "token": address,
            "counted": dist.counted,
            "top10_share": dist.top10_share,
            "deployer_share": dist.deployer_share,
            "clusters": dist.clusters,
            "holders": [asdict(h) for h in dist.holders],
            "logs_read": dist.logs_read,
            "taken_block": head,
        }

    data = cached(f"holders:{address}", 20.0, build)
    if not data:
        return envelope(False, error="Token not found.")
    return envelope(True, data)


def health_route() -> dict:
    out: dict[str, Any] = {"chain_id": CHAIN_ID, "database": "configured" if db.configured() else "absent"}
    try:
        out["head"] = RpcClient().block_number()
        out["rpc"] = "ok"
    except RpcError as exc:
        out["rpc"] = f"unreachable: {exc}"
    if db.configured():
        try:
            out["index"] = db.stats()
        except Exception as exc:  # pragma: no cover
            out["index"] = f"error: {exc}"
    return envelope(True, out)


def handle_get(path: str, query: dict) -> tuple[int, dict] | None:
    if path == "/api/health":
        return 200, health_route()
    if path == "/api/feed":
        return 200, feed_route(query)
    if path.startswith("/api/token/"):
        rest = path[len("/api/token/"):].strip("/")
        if rest.endswith("/holders"):
            return 200, holders_route(rest[: -len("/holders")])
        if rest:
            payload = token_route(rest)
            return (200 if payload["ok"] else 404), payload
    return None


def handle_post(path: str, secret_ok: bool) -> tuple[int, dict] | None:
    if path == "/api/index":
        if not secret_ok:
            return 401, envelope(False, error="Missing or wrong CRON_SECRET.")
        from pipe.indexer import run_all
        try:
            return 200, envelope(True, run_all())
        except Exception as exc:
            return 500, envelope(False, error=str(exc))
    return None
