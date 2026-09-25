from __future__ import annotations

"""
The indexer.

pump.fun serves the live feed well, so unlike the EVM build this is not what
makes the terminal work — it makes it remember. The feed endpoint shows what
is on the front page right now; the database is what lets a coin still be
there tomorrow, with the curve progress it had when you first saw it and the
first moment anything indexed a market for it.

Every run is bounded so it finishes inside a serverless function's budget: one
page of new coins, one page of the ones closest to graduating, one page of the
ones that made it, and a market refresh over whatever it just wrote.
"""

import time

from pipe import db
from pipe.chain import pumpfun
from pipe.chain.rpc import RpcClient, RpcError
from pipe.chain.spl import mint_info_many
from pipe.market import candles
from pipe.market.dexscreener import markets_for

PAGE = 60

# The cron shares one ceiling with every reader: GeckoTerminal allows about two
# calls before it blocks. So a run takes a couple of pools, spaces them, and
# stops the moment it is refused — the next run picks up where this one left
# off, because which pools are due is stored rather than recomputed.
CANDLE_POOLS = 24
CANDLE_PAUSE = 8.0
CANDLE_TTL = 300.0


def index_coins() -> dict:
    coins = {}
    for group in (pumpfun.newest(PAGE), pumpfun.about_to_graduate(30), pumpfun.migrated(30)):
        for coin in group:
            coins.setdefault(coin.mint, coin)
    if not coins:
        return {"found": 0, "written": 0}

    mints = list(coins)
    try:
        info = mint_info_many(RpcClient(), mints)
    except RpcError:
        info = {}

    rows = []
    for mint, coin in coins.items():
        meta = info.get(mint)
        rows.append(
            {
                "mint": mint,
                "symbol": coin.symbol,
                "name": coin.name,
                "creator": coin.creator,
                "bonding_curve": coin.bonding_curve,
                "pool_address": coin.pool_address,
                "created_ms": coin.created_ms,
                "complete": coin.complete,
                "progress": round(coin.progress, 4),
                "decimals": meta.decimals if meta else coin.decimals,
                "mint_readable": bool(meta.readable) if meta else False,
                "can_inflate": bool(meta.can_inflate) if meta else False,
                "can_freeze": bool(meta.can_freeze) if meta else False,
                "image_uri": coin.image_uri,
            }
        )

    written = db.upsert_coins(rows) if db.configured() else 0
    return {"found": len(rows), "written": written}


def refresh_market(limit: int = 90) -> dict:
    if not db.configured():
        return {"updated": 0, "reason": "no database"}
    rows = db.feed(limit=limit, order="new")
    mints = [row["mint"] for row in rows]
    found = markets_for(mints)
    if not found:
        return {"updated": 0, "looked_up": len(mints)}
    payload = [
        {
            "mint": mint,
            "pair_address": m.pair_address,
            "quote_symbol": m.quote_symbol,
            "price_usd": m.price_usd,
            "liquidity_usd": m.liquidity_usd,
            "fdv": m.fdv or m.market_cap,
            "volume_h1": m.volume_h1,
            "volume_h24": m.volume_h24,
            "buys_h1": m.buys_h1,
            "sells_h1": m.sells_h1,
            "change_m5": m.change_m5,
            "change_h1": m.change_h1,
            "change_h24": m.change_h24,
            "image_url": m.image_url,
        }
        for mint, m in found.items()
    ]
    return {"updated": db.upsert_market(payload), "looked_up": len(mints)}


def refresh_candles(budget_seconds: float = 30.0, ttl: float = CANDLE_TTL) -> dict:
    """
    Keeps candles warm for the deepest pools, and — the part that matters more —
    lets history accumulate. One call returns a window; storing every window and
    merging them means the chart eventually reaches further back than any single
    call to GeckoTerminal could.

    The run is bounded twice over: by a time budget, so it finishes inside the
    function's own limit, and by the rate ceiling, which ends it early rather
    than spending the rest of the run collecting refusals.
    """
    if not db.configured():
        return {"pools": 0, "reason": "no database"}
    deadline = time.monotonic() + max(0.0, budget_seconds)
    stored = 0
    fetched = 0
    considered = 0
    for pool in db.charted_pools(CANDLE_POOLS):
        for source in ("1m", "1h"):
            if time.monotonic() >= deadline:
                return {"pools": considered, "fetched": fetched, "bars": stored, "stopped": "out of time"}
            if candles.throttled():
                return {"pools": considered, "fetched": fetched, "bars": stored, "stopped": "rate limited"}
            # The claim is what makes this resumable: a pool refreshed by an
            # earlier run, or by a reader, is skipped without a call.
            if not db.claim_candle_fetch(pool, source, ttl):
                continue
            considered += 1
            bars = candles.fetch_source(pool, source, 1000)
            if bars:
                stored += db.save_candles(pool, source, bars)
                fetched += 1
            time.sleep(CANDLE_PAUSE)
    return {"pools": considered, "fetched": fetched, "bars": stored}


def run_all() -> dict:
    started = time.time()
    if db.configured():
        db.migrate()
    coins = index_coins()
    market = refresh_market()
    # Whatever is left of the function's minute goes on candles, with a few
    # seconds held back so the response itself is never the thing that times out.
    # Measured on Vercel: coins and market take a few seconds, candles fill the
    # rest, and the whole run came back at 54.9s against a 60s ceiling. Pulling
    # the budget back to 45 leaves the response room to be written.
    candle = refresh_candles(budget_seconds=max(0.0, 45.0 - (time.time() - started)))
    return {
        "ok": True,
        "seconds": round(time.time() - started, 2),
        "coins": coins,
        "market": market,
        "candles": candle,
    }
