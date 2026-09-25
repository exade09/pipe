from __future__ import annotations

"""
Postgres, and what it is actually for here.

pump.fun serves the live feed well, so unlike a chain you have to scan
yourself, the database is not what makes this terminal work — it is what makes
it remember. The feed endpoint shows the front page as it is now. The database
is what lets a coin still be findable tomorrow, with the curve progress it had
when it first appeared and the moment anything first indexed a market for it.

Everything degrades to "no database" rather than failing: with DATABASE_URL
unset the routes read pump.fun, the mint accounts and DexScreener live on
every request, and say so in the payload.
"""

import json
from contextlib import contextmanager
from typing import Any, Iterator

from pipe.config import database_url

try:  # psycopg is only needed when a database is configured
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - exercised by the no-database path
    psycopg = None
    dict_row = None


SCHEMA = """
create table if not exists coins (
  mint          text primary key,
  symbol        text not null default '',
  name          text not null default '',
  creator       text not null default '',
  bonding_curve text not null default '',
  pool_address  text not null default '',
  created_ms    bigint not null default 0,
  complete      boolean not null default false,
  progress      double precision not null default 0,
  decimals      int not null default 6,
  mint_readable boolean not null default false,
  can_inflate   boolean not null default false,
  can_freeze    boolean not null default false,
  image_uri     text not null default '',
  first_seen    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index if not exists coins_created_idx on coins (created_ms desc);
create index if not exists coins_progress_idx on coins (complete, progress desc);

create table if not exists market (
  mint           text primary key references coins(mint) on delete cascade,
  pair_address   text not null default '',
  quote_symbol   text not null default '',
  price_usd      double precision not null default 0,
  liquidity_usd  double precision not null default 0,
  fdv            double precision not null default 0,
  volume_h1      double precision not null default 0,
  volume_h24     double precision not null default 0,
  buys_h1        int not null default 0,
  sells_h1       int not null default 0,
  change_m5      double precision not null default 0,
  change_h1      double precision not null default 0,
  change_h24     double precision not null default 0,
  image_url      text not null default '',
  fetched_at     timestamptz not null default now()
);
create index if not exists market_liquidity_idx on market (liquidity_usd desc);

-- Candles, and the reason they are in here rather than in memory.
--
-- GeckoTerminal is the only source that serves Solana OHLCV without a key,
-- and its free tier allows about two calls a minute. In one long-lived
-- process an in-memory cache hides that. On Vercel it does not: every request
-- may land on a different instance with its own empty memory, so the same
-- pool gets asked for over and over and the ceiling is hit almost at once.
--
-- One shared table fixes both halves. Bars fetched by any instance are read
-- by all of them, and `candle_fetch` is the lock that decides which single
-- instance is allowed to go upstream at all.
create table if not exists candles (
  pool      text not null,
  timeframe text not null,
  t         bigint not null,
  o         double precision not null,
  h         double precision not null,
  l         double precision not null,
  c         double precision not null,
  v         double precision not null,
  primary key (pool, timeframe, t)
);
create index if not exists candles_read_idx on candles (pool, timeframe, t desc);

create table if not exists candle_fetch (
  pool       text not null,
  timeframe  text not null,
  fetched_at timestamptz not null default now(),
  primary key (pool, timeframe)
);

create table if not exists holders_snapshot (
  mint           text primary key references coins(mint) on delete cascade,
  counted        int not null default 0,
  top10_share    double precision not null default 0,
  creator_share  double precision not null default 0,
  curve_share    double precision not null default 0,
  holders        jsonb not null default '[]'::jsonb,
  taken_at       timestamptz not null default now()
);
"""


def configured() -> bool:
    return bool(database_url()) and psycopg is not None


@contextmanager
def connect() -> Iterator[Any]:
    if not configured():
        raise RuntimeError("no database configured")
    with psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=8) as conn:
        yield conn


def migrate() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)
        conn.commit()


# ---------------------------------------------------------------- writes

def upsert_coins(rows: list[dict]) -> int:
    if not rows:
        return 0
    with connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                insert into coins
                  (mint, symbol, name, creator, bonding_curve, pool_address, created_ms,
                   complete, progress, decimals, mint_readable, can_inflate, can_freeze, image_uri)
                values
                  (%(mint)s, %(symbol)s, %(name)s, %(creator)s, %(bonding_curve)s,
                   %(pool_address)s, %(created_ms)s, %(complete)s, %(progress)s, %(decimals)s,
                   %(mint_readable)s, %(can_inflate)s, %(can_freeze)s, %(image_uri)s)
                on conflict (mint) do update set
                  symbol = excluded.symbol,
                  name = excluded.name,
                  pool_address = excluded.pool_address,
                  complete = excluded.complete,
                  progress = excluded.progress,
                  -- authorities can be revoked after launch, so a later read
                  -- of "revoked" must be allowed to overwrite an earlier
                  -- "live". The reverse cannot happen on this chain.
                  mint_readable = excluded.mint_readable or coins.mint_readable,
                  can_inflate = excluded.can_inflate,
                  can_freeze = excluded.can_freeze,
                  updated_at = now()
                """,
                rows,
            )
        conn.commit()
    return len(rows)


def upsert_market(rows: list[dict]) -> int:
    if not rows:
        return 0
    with connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                insert into market
                  (mint, pair_address, quote_symbol, price_usd, liquidity_usd, fdv,
                   volume_h1, volume_h24, buys_h1, sells_h1,
                   change_m5, change_h1, change_h24, image_url, fetched_at)
                values
                  (%(mint)s, %(pair_address)s, %(quote_symbol)s, %(price_usd)s,
                   %(liquidity_usd)s, %(fdv)s, %(volume_h1)s, %(volume_h24)s,
                   %(buys_h1)s, %(sells_h1)s, %(change_m5)s, %(change_h1)s,
                   %(change_h24)s, %(image_url)s, now())
                on conflict (mint) do update set
                  pair_address = excluded.pair_address,
                  quote_symbol = excluded.quote_symbol,
                  price_usd = excluded.price_usd,
                  liquidity_usd = excluded.liquidity_usd,
                  fdv = excluded.fdv,
                  volume_h1 = excluded.volume_h1,
                  volume_h24 = excluded.volume_h24,
                  buys_h1 = excluded.buys_h1,
                  sells_h1 = excluded.sells_h1,
                  change_m5 = excluded.change_m5,
                  change_h1 = excluded.change_h1,
                  change_h24 = excluded.change_h24,
                  image_url = case when excluded.image_url <> '' then excluded.image_url else market.image_url end,
                  fetched_at = now()
                """,
                rows,
            )
        conn.commit()
    return len(rows)


def save_holders(mint: str, payload: dict) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into holders_snapshot
                  (mint, counted, top10_share, creator_share, curve_share, holders, taken_at)
                values (%s, %s, %s, %s, %s, %s, now())
                on conflict (mint) do update set
                  counted = excluded.counted,
                  top10_share = excluded.top10_share,
                  creator_share = excluded.creator_share,
                  curve_share = excluded.curve_share,
                  holders = excluded.holders,
                  taken_at = now()
                """,
                (
                    mint,
                    payload.get("counted", 0),
                    payload.get("top10_share", 0.0),
                    payload.get("creator_share", 0.0),
                    payload.get("curve_share", 0.0),
                    json.dumps(payload.get("holders", [])),
                ),
            )
        conn.commit()


def claim_candle_fetch(pool: str, timeframe: str, ttl_seconds: float) -> bool:
    """
    Whether this instance is the one that goes to GeckoTerminal.

    The insert succeeds only if nobody has fetched this pair inside the TTL, and
    it succeeds for exactly one caller because the primary key serialises them.
    Everyone who loses reads the bars the winner is about to write, which is the
    whole point: a hundred readers on a hundred instances cost one upstream
    call between them rather than a hundred refusals.
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into candle_fetch (pool, timeframe, fetched_at)
                values (%s, %s, now())
                on conflict (pool, timeframe) do update set fetched_at = now()
                where candle_fetch.fetched_at < now() - make_interval(secs => %s)
                returning pool
                """,
                (pool, timeframe, float(ttl_seconds)),
            )
            won = cur.fetchone() is not None
        conn.commit()
    return won


def save_candles(pool: str, timeframe: str, bars: list[dict]) -> int:
    """
    Bars are immutable once closed, but the newest one is still forming — so the
    write updates on conflict rather than ignoring it, and a bar that was half
    built when it was first stored ends up complete.
    """
    if not bars:
        return 0
    rows = [
        (pool, timeframe, int(b["t"]), float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"]), float(b["v"]))
        for b in bars
    ]
    with connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                insert into candles (pool, timeframe, t, o, h, l, c, v)
                values (%s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (pool, timeframe, t) do update set
                  o = excluded.o, h = excluded.h, l = excluded.l,
                  c = excluded.c, v = excluded.v
                """,
                rows,
            )
        conn.commit()
    return len(rows)


# ---------------------------------------------------------------- reads

def read_candles(pool: str, timeframe: str, limit: int = 1000) -> list[dict]:
    """Oldest first, because that is the direction a chart is drawn in."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select t, o, h, l, c, v from candles
            where pool = %s and timeframe = %s
            order by t desc limit %s
            """,
            (pool, timeframe, int(limit)),
        )
        rows = [
            {"t": int(r["t"]), "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"], "v": r["v"]}
            for r in cur.fetchall()
        ]
    rows.reverse()
    return rows


def candle_age(pool: str, timeframe: str) -> float | None:
    """Seconds since anything last went upstream for this pair, or None."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select extract(epoch from (now() - fetched_at)) as age from candle_fetch where pool = %s and timeframe = %s",
            (pool, timeframe),
        )
        row = cur.fetchone()
        return float(row["age"]) if row and row["age"] is not None else None


def charted_pools(limit: int = 12) -> list[str]:
    """
    The pools worth keeping candles for between visits: the deepest ones, which
    are the ones somebody is most likely to open next.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select pair_address from market
            where pair_address <> ''
            order by liquidity_usd desc limit %s
            """,
            (int(limit),),
        )
        return [row["pair_address"] for row in cur.fetchall()]

FEED_SQL = """
select c.mint, c.symbol, c.name, c.creator, c.bonding_curve, c.pool_address, c.created_ms,
       c.complete, c.progress, c.decimals, c.mint_readable, c.can_inflate, c.can_freeze,
       coalesce(nullif(m.image_url,''), c.image_uri) as image_url,
       coalesce(m.price_usd,0)     as price_usd,
       coalesce(m.liquidity_usd,0) as liquidity_usd,
       coalesce(m.fdv,0)           as fdv,
       coalesce(m.volume_h1,0)     as volume_h1,
       coalesce(m.volume_h24,0)    as volume_h24,
       coalesce(m.buys_h1,0)       as buys_h1,
       coalesce(m.sells_h1,0)      as sells_h1,
       coalesce(m.change_m5,0)     as change_m5,
       coalesce(m.change_h1,0)     as change_h1,
       coalesce(m.change_h24,0)    as change_h24,
       coalesce(m.quote_symbol,'') as quote_symbol,
       coalesce(h.top10_share,0)   as top10_share,
       coalesce(h.creator_share,0) as creator_share,
       coalesce(h.counted,0)       as holders_counted
from coins c
left join market m on m.mint = c.mint
left join holders_snapshot h on h.mint = c.mint
"""

ORDERS = {
    "new": "order by c.created_ms desc",
    "stretch": "where c.complete = false order by c.progress desc",
    "migrated": "where c.complete = true order by coalesce(m.liquidity_usd,0) desc",
    "liquidity": "order by coalesce(m.liquidity_usd,0) desc",
}


def feed(*, limit: int = 60, order: str = "new") -> list[dict]:
    clause = ORDERS.get(order, ORDERS["new"])
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"{FEED_SQL} {clause} limit %s", (limit,))
        return [dict(row) for row in cur.fetchall()]


def coin(mint: str) -> dict | None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"{FEED_SQL} where c.mint = %s", (mint,))
        row = cur.fetchone()
        return dict(row) if row else None


def holders(mint: str) -> dict | None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("select * from holders_snapshot where mint = %s", (mint,))
        row = cur.fetchone()
        return dict(row) if row else None


def stats() -> dict:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("select count(*) as n from coins")
        total = cur.fetchone()["n"]
        cur.execute("select count(*) as n from coins where complete")
        done = cur.fetchone()["n"]
        cur.execute("select count(*) as n from candles")
        bars = cur.fetchone()["n"]
        cur.execute("select count(*) as n from candle_fetch")
        pairs = cur.fetchone()["n"]
        return {"coins": total, "migrated": done, "candles": bars, "charted_pairs": pairs}
