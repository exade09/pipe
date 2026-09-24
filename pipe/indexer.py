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
from pipe.market.dexscreener import markets_for

PAGE = 60


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


def run_all() -> dict:
    started = time.time()
    if db.configured():
        db.migrate()
    coins = index_coins()
    market = refresh_market()
    return {
        "ok": True,
        "seconds": round(time.time() - started, 2),
        "coins": coins,
        "market": market,
    }
