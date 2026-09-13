from __future__ import annotations

"""
Postgres, and the reason there has to be one.

Blocks land every 0.1 seconds and roughly sixty tokens launch every seven
minutes. A request that goes to the chain for "the last hour of launches" is
asking for 36,000 blocks of logs on every page load, which is neither fast
nor free. The indexer walks the chain once and writes here; the API reads
here and never scans.

Everything degrades to "no database" rather than failing: with DATABASE_URL
unset the routes fall back to reading a short window straight off the chain.
That path is the local-development path and the first-deploy path, and it is
honest about being a smaller window rather than pretending to be the feed.
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
create table if not exists tokens (
  address       text primary key,
  curve         text not null,
  deployer      text not null,
  pair_token    text not null default '',
  launch_block  bigint not null,
  launch_tx     text not null default '',
  name          text not null default '',
  symbol        text not null default '',
  decimals      int  not null default 18,
  total_supply  numeric not null default 0,
  first_seen    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index if not exists tokens_launch_block_idx on tokens (launch_block desc);

create table if not exists market (
  address        text primary key references tokens(address) on delete cascade,
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

create table if not exists holders_snapshot (
  address        text primary key references tokens(address) on delete cascade,
  counted        int not null default 0,
  top10_share    double precision not null default 0,
  deployer_share double precision not null default 0,
  clusters       jsonb not null default '[]'::jsonb,
  holders        jsonb not null default '[]'::jsonb,
  taken_block    bigint not null default 0,
  taken_at       timestamptz not null default now()
);

create table if not exists cursors (
  name  text primary key,
  value bigint not null
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


# ---------------------------------------------------------------- cursors

def get_cursor(name: str, default: int = 0) -> int:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("select value from cursors where name = %s", (name,))
        row = cur.fetchone()
        return int(row["value"]) if row else default


def set_cursor(name: str, value: int) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into cursors (name, value) values (%s, %s) "
                "on conflict (name) do update set value = excluded.value",
                (name, value),
            )
        conn.commit()


# ---------------------------------------------------------------- writes

def upsert_tokens(rows: list[dict]) -> int:
    if not rows:
        return 0
    with connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                insert into tokens
                  (address, curve, deployer, pair_token, launch_block, launch_tx,
                   name, symbol, decimals, total_supply)
                values
                  (%(address)s, %(curve)s, %(deployer)s, %(pair_token)s, %(launch_block)s,
                   %(launch_tx)s, %(name)s, %(symbol)s, %(decimals)s, %(total_supply)s)
                on conflict (address) do update set
                  name = excluded.name,
                  symbol = excluded.symbol,
                  decimals = excluded.decimals,
                  total_supply = excluded.total_supply,
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
                  (address, pair_address, quote_symbol, price_usd, liquidity_usd, fdv,
                   volume_h1, volume_h24, buys_h1, sells_h1,
                   change_m5, change_h1, change_h24, image_url, fetched_at)
                values
                  (%(address)s, %(pair_address)s, %(quote_symbol)s, %(price_usd)s,
                   %(liquidity_usd)s, %(fdv)s, %(volume_h1)s, %(volume_h24)s,
                   %(buys_h1)s, %(sells_h1)s, %(change_m5)s, %(change_h1)s,
                   %(change_h24)s, %(image_url)s, now())
                on conflict (address) do update set
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


def save_holders(address: str, payload: dict) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into holders_snapshot
                  (address, counted, top10_share, deployer_share, clusters, holders, taken_block, taken_at)
                values (%s, %s, %s, %s, %s, %s, %s, now())
                on conflict (address) do update set
                  counted = excluded.counted,
                  top10_share = excluded.top10_share,
                  deployer_share = excluded.deployer_share,
                  clusters = excluded.clusters,
                  holders = excluded.holders,
                  taken_block = excluded.taken_block,
                  taken_at = now()
                """,
                (
                    address.lower(),
                    payload.get("counted", 0),
                    payload.get("top10_share", 0.0),
                    payload.get("deployer_share", 0.0),
                    json.dumps(payload.get("clusters", [])),
                    json.dumps(payload.get("holders", [])),
                    payload.get("taken_block", 0),
                ),
            )
        conn.commit()


# ---------------------------------------------------------------- reads

FEED_SQL = """
select t.address, t.curve, t.deployer, t.pair_token, t.launch_block, t.symbol, t.name,
       t.decimals, t.total_supply, t.first_seen,
       coalesce(m.price_usd,0) as price_usd,
       coalesce(m.liquidity_usd,0) as liquidity_usd,
       coalesce(m.fdv,0) as fdv,
       coalesce(m.volume_h1,0) as volume_h1,
       coalesce(m.volume_h24,0) as volume_h24,
       coalesce(m.buys_h1,0) as buys_h1,
       coalesce(m.sells_h1,0) as sells_h1,
       coalesce(m.change_m5,0) as change_m5,
       coalesce(m.change_h1,0) as change_h1,
       coalesce(m.change_h24,0) as change_h24,
       coalesce(m.image_url,'') as image_url,
       coalesce(m.quote_symbol,'') as quote_symbol,
       coalesce(h.top10_share,0) as top10_share,
       coalesce(h.deployer_share,0) as deployer_share,
       coalesce(h.counted,0) as holders_counted
from tokens t
left join market m on m.address = t.address
left join holders_snapshot h on h.address = t.address
"""


def feed(*, limit: int = 60, min_liquidity: float = 0.0, order: str = "new") -> list[dict]:
    where = "where coalesce(m.liquidity_usd,0) >= %s"
    order_sql = {
        "new": "order by t.launch_block desc",
        "liquidity": "order by coalesce(m.liquidity_usd,0) desc",
        "volume": "order by coalesce(m.volume_h1,0) desc",
    }.get(order, "order by t.launch_block desc")
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"{FEED_SQL} {where} {order_sql} limit %s", (min_liquidity, limit))
        return [dict(row) for row in cur.fetchall()]


def token(address: str) -> dict | None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"{FEED_SQL} where t.address = %s", (address.lower(),))
        row = cur.fetchone()
        return dict(row) if row else None


def holders(address: str) -> dict | None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("select * from holders_snapshot where address = %s", (address.lower(),))
        row = cur.fetchone()
        return dict(row) if row else None


def stats() -> dict:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("select count(*) as n from tokens")
        total = cur.fetchone()["n"]
        cur.execute("select count(*) as n from market where liquidity_usd > 0")
        priced = cur.fetchone()["n"]
        return {"tokens": total, "priced": priced}
