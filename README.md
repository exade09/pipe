# Pipe Terminal

A trading terminal for Robinhood Chain: the launch feed, token detail, holder
distribution and the bubble map, plus a written read on every token instead of
a score out of a hundred.

Separate project, separate repository, separate Vercel deployment.

## Where the data comes from

Three sources, all verified against the live chain rather than assumed.

**The chain — `https://rpc.mainnet.chain.robinhood.com`** is the source of
truth for what exists. Every tradable token here is launched through the Pons
factory at `0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e`, and every launch emits
one `TokenLaunched` log. That log is the entire discovery feed.

> The RPC answers **403 with an empty body** to any request without a
> `User-Agent`, which looks exactly like the node being down. Every request in
> `pipe/chain/rpc.py` sets one. Do not remove it.

**DexScreener — chain id `robinhood`** is the source for price, liquidity,
volume, buy/sell counts and, through `info.imageUrl`, the token avatars. No key,
no auth.

> DexScreener has not heard of a token for its first minutes. A fresh row comes
> back with `indexed: false` and zero liquidity. That is correct and expected —
> the chain already told us the token exists, and the feed shows it immediately
> rather than waiting for an indexer somewhere else to catch up.

**Holders are computed here, not fetched.** The chain's Blockscout explorer sits
behind bot protection and answers 403 to anything that is not a browser, so its
holder endpoint is unusable from a server. It turns out not to matter: tokens
here are minutes to hours old, so replaying their whole `Transfer` history is a
handful of logs. A twenty-minute-old token took 25 logs and 1.8 seconds.

Two exclusions in that calculation are deliberate. The **curve** holds every
token nobody has bought yet, so counting it makes every new launch look like a
96% rug. The zero and dead addresses are burns, not people.

## Why there has to be a database

Blocks land every **0.1 seconds** and roughly **sixty tokens launch every seven
minutes** — about thirteen thousand a day. "The last hour of launches" is 36,000
blocks of logs on every page load. The indexer walks the chain once, keeps a
cursor, and writes to Postgres; the API reads Postgres and never scans.

With `DATABASE_URL` unset everything still runs, reading a live twelve-minute
window straight off the chain. The response says `source: "chain"` and carries a
note about the window, so the UI can tell the user it is small rather than
showing a short feed and looking broken.

## Layout

```
api/index.py          Vercel entry: API, and web/dist for everything else
pipe/config.py        endpoints, chain id, block time, all env-overridable
pipe/chain/rpc.py     JSON-RPC with the required User-Agent, batching, retries
pipe/chain/pons.py    TokenLaunched decoding — the discovery feed
pipe/chain/erc20.py   name/symbol/decimals/supply, four calls per token, one batch
pipe/chain/holders.py distribution and clusters from Transfer logs
pipe/market/dexscreener.py  price, liquidity, volume, avatars
pipe/db.py            Postgres schema, upserts, feed queries
pipe/indexer.py       cursor-driven: launches, then metadata, then market
pipe_api/dispatch.py  routes
web/                  the terminal itself (Vite + React)
```

## Endpoints

| | |
|---|---|
| `GET /api/health` | chain id, head block, whether a database is attached |
| `GET /api/feed?limit=&order=&min_liquidity=` | the feed. `order` is `new`, `liquidity` or `volume` |
| `GET /api/token/{address}` | one token, plus its last holder snapshot |
| `GET /api/token/{address}/holders` | distribution and clusters for the bubble map |
| `POST /api/index` | runs the indexer. Requires `Authorization: Bearer $CRON_SECRET` |

## Running it

```bash
pip install -r requirements.txt
npm --prefix web install
```

Local, without a database — the twelve-minute window:

```bash
python -c "from pipe_api.dispatch import handle_get; print(handle_get('/api/feed',{})[1])"
```

With one, create the tables and fill them:

```bash
export DATABASE_URL="postgres://…"
python -c "from pipe.indexer import run_all; print(run_all())"
```

## Environment

| | |
|---|---|
| `DATABASE_URL` | Vercel Postgres or Neon. Absent means the chain-window mode |
| `CRON_SECRET` | required before `/api/index` will do anything |
| `ROBINHOOD_RPC_URL` | overrides the default RPC |
| `PONS_FACTORY` | overrides the factory address |
| `PIPE_USER_AGENT` | what the RPC sees. Must not be empty |

## Two things to know before deploying

**The cron in `vercel.json` runs every minute.** Minute-level schedules need a
Pro plan; on Hobby, Vercel silently reduces it to daily, which is useless for a
feed. Either upgrade or run the indexer from somewhere else and keep the route
as the endpoint it calls.

**One indexer run is bounded to 60,000 blocks** so it always finishes inside the
function's time budget. After an outage it catches up over several runs instead
of timing out forever on the first one.
