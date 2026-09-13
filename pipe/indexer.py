from __future__ import annotations

"""
The indexer.

It does three things, in this order, and each one is bounded so a single run
can never take longer than a serverless function is allowed to live:

  1. read TokenLaunched logs from wherever it stopped last time
  2. read name/symbol/decimals/supply for whatever is new, in one batch
  3. refresh market data for the most recently launched tokens

The cursor is the whole design. Without it every run re-reads the same window
and the feed is whatever the last sixty seconds happened to contain; with it
the database accumulates a real history of a chain that produces ten blocks a
second.

A first run on an empty database does not try to index from genesis. It starts
one hour back, because a terminal shows what is trading now and a backfill is
a separate job with a separate budget.
"""

import time
from dataclasses import asdict

from pipe.chain.erc20 import metadata_many
from pipe.chain.holders import distribution
from pipe.chain.pons import launches_between
from pipe.chain.rpc import RpcClient
from pipe.config import blocks_for_minutes
from pipe.market.dexscreener import markets_for
from pipe import db

CURSOR = "pons_launches"

# One run never walks more than this, so the function finishes inside its
# time budget even after an outage. Catching up simply takes several runs.
MAX_BLOCKS_PER_RUN = 60_000
# Cold start: an hour of history, not the whole chain.
COLD_START_MINUTES = 60


def _sanitise(text: str, limit: int = 64) -> str:
    """
    Names and symbols come from contracts anybody can deploy. Strip control
    characters here so nothing downstream has to remember to.
    """
    cleaned = "".join(ch for ch in (text or "") if ch.isprintable())
    return cleaned.strip()[:limit]


def index_launches(client: RpcClient | None = None) -> dict:
    client = client or RpcClient()
    head = client.block_number()

    if db.configured():
        last = db.get_cursor(CURSOR, 0)
    else:
        last = 0

    if last <= 0:
        start = head - blocks_for_minutes(COLD_START_MINUTES)
    else:
        start = last + 1
    start = max(start, head - MAX_BLOCKS_PER_RUN)
    if start > head:
        return {"scanned": 0, "found": 0, "head": head, "from": start}

    launches = launches_between(client, start, head)
    if not launches:
        if db.configured():
            db.set_cursor(CURSOR, head)
        return {"scanned": head - start + 1, "found": 0, "head": head, "from": start}

    addresses = [item.token for item in launches]
    meta = metadata_many(client, addresses)

    rows = []
    for item in launches:
        info = meta.get(item.token)
        rows.append(
            {
                "address": item.token,
                "curve": item.curve,
                "deployer": item.deployer,
                "pair_token": item.pair_token,
                "launch_block": item.block,
                "launch_tx": item.tx,
                "name": _sanitise(info.name if info else ""),
                "symbol": _sanitise(info.symbol if info else "", 24),
                "decimals": info.decimals if info else 18,
                "total_supply": str(info.total_supply if info else 0),
            }
        )

    written = db.upsert_tokens(rows) if db.configured() else 0
    if db.configured():
        db.set_cursor(CURSOR, head)

    return {
        "scanned": head - start + 1,
        "found": len(rows),
        "written": written,
        "head": head,
        "from": start,
    }


def refresh_market(limit: int = 90) -> dict:
    """
    Market data for the newest tokens. DexScreener has not heard of a token
    for its first minutes, so rows come back missing and that is expected —
    the chain already told us the token exists.
    """
    if not db.configured():
        return {"updated": 0, "reason": "no database"}

    rows = db.feed(limit=limit, order="new")
    addresses = [row["address"] for row in rows]
    found = markets_for(addresses)
    if not found:
        return {"updated": 0, "looked_up": len(addresses)}

    payload = []
    for address, market in found.items():
        payload.append(
            {
                "address": address,
                "pair_address": market.pair_address,
                "quote_symbol": market.quote_symbol,
                "price_usd": market.price_usd,
                "liquidity_usd": market.liquidity_usd,
                "fdv": market.fdv or market.market_cap,
                "volume_h1": market.volume_h1,
                "volume_h24": market.volume_h24,
                "buys_h1": market.buys_h1,
                "sells_h1": market.sells_h1,
                "change_m5": market.change_m5,
                "change_h1": market.change_h1,
                "change_h24": market.change_h24,
                "image_url": market.image_url,
            }
        )
    return {"updated": db.upsert_market(payload), "looked_up": len(addresses)}


def refresh_holders(limit: int = 12, client: RpcClient | None = None) -> dict:
    """
    Holder distribution is the most expensive read here, so it is done for a
    few tokens per run rather than all of them — the ones with the deepest
    liquidity, because those are the rows anybody actually opens.
    """
    if not db.configured():
        return {"updated": 0, "reason": "no database"}
    client = client or RpcClient()
    rows = db.feed(limit=limit, order="liquidity", min_liquidity=1.0)
    head = client.block_number()
    done = 0
    for row in rows:
        try:
            dist = distribution(
                client,
                token=row["address"],
                curve=row["curve"],
                deployer=row["deployer"],
                from_block=int(row["launch_block"]),
                to_block=head,
                limit=60,
            )
        except Exception:
            continue
        db.save_holders(
            row["address"],
            {
                "counted": dist.counted,
                "top10_share": dist.top10_share,
                "deployer_share": dist.deployer_share,
                "clusters": dist.clusters,
                "holders": [asdict(h) for h in dist.holders],
                "taken_block": head,
            },
        )
        done += 1
    return {"updated": done}


def run_all() -> dict:
    started = time.time()
    if db.configured():
        db.migrate()
    launches = index_launches()
    market = refresh_market()
    holders = refresh_holders()
    return {
        "ok": True,
        "seconds": round(time.time() - started, 2),
        "launches": launches,
        "market": market,
        "holders": holders,
    }
