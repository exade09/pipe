# Pipe Terminal — Solana

A trading terminal for Solana: the launch feed straight off pump.fun, the two
mint authorities that decide whether a coin can be turned against you, holder
distribution and the bubble map, and a written read on every coin instead of a
score out of a hundred.

## Where the data comes from

Three sources, each verified against live responses rather than assumed, and
each doing the one thing it is best at.

**pump.fun — `frontend-api-v3.pump.fun`** is the source of truth for existence.
It gives the creator, the bonding curve account, the reserves and `complete`,
which is the only authoritative answer to whether a coin has migrated.

> The older `frontend-api` host answers **530**. Only `frontend-api-v3` works,
> and only with a browser-shaped `User-Agent`. A library default gets nothing.

> `complete=false` is a supported query parameter and it matters: sorting by
> market cap without it returns a page that is almost entirely coins which
> already migrated, and filtering afterwards leaves an empty column.

**The mint account** gives the two facts that matter most, and the public RPC
serves them without a key:

| | |
|---|---|
| `mintAuthority` | if set, more supply can be created at any moment |
| `freezeAuthority` | if set, a balance can be frozen in the wallet holding it |

**DexScreener — chain id `solana`** supplies price, liquidity, volume, buy and
sell counts, and a second source for the image. No key, no auth. It knows
nothing about a coin still on the curve, which is normal rather than an error.

## The one thing that needs a key

`getTokenLargestAccounts` is the holder call, and **no free Solana endpoint
will serve it**. Measured, not assumed:

| endpoint | answer |
|---|---|
| api.mainnet-beta.solana.com | 429 |
| rpc.ankr.com/solana | 403 |
| solana-rpc.publicnode.com | 403 |
| solana.drpc.org | 400 |

So holders and the bubble map are gated behind `HELIUS_API_KEY` or
`SOLANA_RPC_URL`. Without one the terminal says so on the token page instead of
drawing an empty chart that reads as "nobody holds this". Everything else —
the feed, the curve, both authorities, price — works with no key at all.

## What the bubble map does and does not claim

Circles are wallets, area is share, and several token accounts owned by one
wallet collapse into one circle. **No lines are drawn between wallets.** On an
EVM chain the transfer log gives funding relationships for free; on Solana that
needs signature history per wallet, which is a different order of cost, and a
line we have not verified would say more than we know. The creator's wallet is
the one relationship the data does give, and it is marked in copper.

## The read

Every other scanner prints a number out of a hundred. That hides the thing that
matters: a coin with four verified facts and three unverifiable ones is not the
same object as one with seven verified facts, and both come out as 72.

So the read returns what was **checked**, what **failed**, and what **could not
be checked at all** — named rather than folded into a guess. The paragraph is
assembled from the same three lists, so it can never disagree with them.

## Layout

```
api/index.py              Vercel entry: API, and web/dist for everything else
pipe/config.py            endpoints, curve threshold, all env-overridable
pipe/chain/rpc.py         Solana JSON-RPC; refuses the holder call loudly
pipe/chain/pumpfun.py     the launch feed, curve progress, migration flag
pipe/chain/spl.py         mint authorities and supply, one batch per page
pipe/chain/holders.py     distribution from the twenty largest token accounts
pipe/market/dexscreener.py price, liquidity, volume, images
pipe/analysis/read.py     the read — three lists and a paragraph, no score
pipe/db.py                Postgres: history, not the critical path
pipe/indexer.py           writes what the feed showed so it stays findable
pipe_api/dispatch.py      routes
web/                      the terminal (Vite + React)
```

## Endpoints

| | |
|---|---|
| `GET /api/health` | slot, whether holders are available, whether a database is attached |
| `GET /api/feed?limit=` | three columns: new, final stretch, migrated |
| `GET /api/token/{mint}` | one coin, its authorities and its read |
| `GET /api/token/{mint}/holders` | distribution for the bubble map — 409 without a key |
| `POST /api/index` | runs the indexer. Requires `Authorization: Bearer $CRON_SECRET` |

## Running it

```bash
pip install -r requirements.txt
npm --prefix web install && npm --prefix web run build
python dev.py 8000
```

That serves the API and the built frontend on one port, exactly as Vercel does.

## Environment

| | |
|---|---|
| `HELIUS_API_KEY` | unlocks holders and the bubble map |
| `SOLANA_RPC_URL` | a full RPC URL, if you would rather not use Helius |
| `DATABASE_URL` | Vercel Postgres or Neon. Absent means live-only, no history |
| `CRON_SECRET` | required before `/api/index` will do anything |
| `PUMPFUN_BASE` | overrides the launch feed host |
| `PIPE_USER_AGENT` | what the feed sees. Must look like a browser |

## Two things to know before deploying

**The cron in `vercel.json` runs every minute.** Minute-level schedules need a
Pro plan; on Hobby, Vercel quietly reduces it to daily. The terminal still
works — the feed is live either way — but nothing accumulates.

**Trading is not wired.** The order panel is present and disabled, and says so.
There is no wallet adapter, no signing and no approvals: nothing can leave an
account from this screen.

---

The Robinhood Chain version of this terminal is in the history at commit
`befacc6`, including its Pons log reader and the EVM holder replay.
