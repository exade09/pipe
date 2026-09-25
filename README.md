# PIPE Terminal

PIPE is a live Solana token terminal for launch discovery, market structure,
authority checks, holder concentration, execution and grounded AI analysis.

Production: https://pipe-ten-zeta.vercel.app/

Product documentation is part of the site at `/docs`. The terminal header
also contains the project token CA slot and the animated
[@pipeterminal](https://x.com/pipeterminal) link.

## Product principles

- Show verified facts, explicit flags and explicit unknowns.
- Never convert unavailable data into a zero or a clean state.
- Keep wallet signing in the wallet. The server only builds unsigned swaps.
- Keep paid credentials server-side.
- Present concentration honestly: the bubble map does not invent wallet links.

## Architecture

```text
api/index.py              Vercel entry: API plus built SPA fallback
pipe_api/dispatch.py      API routing, envelopes and request limits
pipe/analysis/agent.py    Fable 5.1 server-side analysis
pipe/analysis/read.py     deterministic checked/flagged/unknown read
pipe/chain/               Solana RPC, mint authorities and holder resolution
pipe/market/              market data, candles and swap routing
pipe/db.py                optional shared history/cache database
web/src/App.jsx           terminal shell
web/src/Agent.jsx         working Fable 5.1 agent dock
web/src/BubbleMap.jsx     interactive holder concentration map
web/src/Docs.jsx          public product manual at /docs
```

Vercel builds the Vite frontend into `web/dist`. The Python function serves
API routes and falls back to `index.html` for client routes such as
`/docs`.

## Fable 5.1

The product-facing agent runtime is **Fable 5.1**. The implementation calls
the OpenAI Responses API from the Python server with `gpt-6-astra` by default.

The browser sends only a mint and a question. The server:

1. validates and rate-limits the request;
2. loads the token's verified market and authority facts;
3. adds holder concentration when a keyed RPC is available;
4. treats token metadata as untrusted data;
5. requests a strict structured response;
6. returns evidence, risks, unknowns and confidence.

`OPENAI_API_KEY` is read only by the server. Never prefix it with `VITE_`
and never commit it.

## Bubble map

The map reads the largest token accounts and resolves each token account to
its owning wallet. Multiple token accounts owned by the same wallet collapse
into one circle.

- Circle area represents share of the observed holder set.
- Creator ownership is highlighted in copper.
- Hover, keyboard focus and selection reveal wallet details.
- Top-ten and creator concentration remain visible above the map.
- No wallet-to-wallet relationship is drawn without verified transfer history.

Holder data requires `HELIUS_API_KEY` or `SOLANA_RPC_URL`. Without either,
the terminal reports that the check is unavailable instead of drawing an
empty map.

## Local development

```bash
python -m pip install -r requirements.txt
npm --prefix web install
npm --prefix web run build
python dev.py 8000
```

Open http://127.0.0.1:8000/. Documentation is at
http://127.0.0.1:8000/docs.

For frontend hot reload:

```bash
npm --prefix web run dev
```

Vite proxies `/api` according to `web/vite.config.js`.

## Environment

Copy `.env.example` into your local secret manager or configure the values
directly in Vercel.

| Variable | Scope | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | server only | Enables Fable 5.1 analysis |
| `OPENAI_MODEL` | server only | Optional model override; defaults to `gpt-6-astra` |
| `VITE_TOKEN_CA` | public build value | Project token contract address shown in the header |
| `HELIUS_API_KEY` | server only | Enables holder resolution and bubble map |
| `SOLANA_RPC_URL` | server only | Alternative keyed Solana RPC |
| `DATABASE_URL` | server only | Shared candles/history across Vercel instances |
| `CRON_SECRET` | server only | Protects the index cron endpoint |
| `JUPITER_BASE` | server only | Optional swap router override |

The CA is intentionally rendered as `CA: TBA` until `VITE_TOKEN_CA` is
set and a new frontend build is deployed.

## API

All routes use `{ ok, data, error }`.

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/health` | RPC, holders, database and Fable 5.1 status |
| GET | `/api/feed?limit=` | New, final-stretch and migrated launch activity |
| GET | `/api/token/{mint}` | Token market state, authorities and deterministic read |
| GET | `/api/token/{mint}/holders` | Holder distribution for table and bubble map |
| GET | `/api/token/{mint}/candles?tf=` | OHLCV series |
| GET | `/api/wallet/{owner}?mint=` | Connected wallet balances |
| GET | `/api/tx/{signature}` | Submitted swap status |
| POST | `/api/agent/analyze` | Grounded Fable 5.1 token analysis |
| POST | `/api/quote` | Live swap route |
| POST | `/api/swap` | Unsigned swap transaction |
| POST | `/api/index` | Protected cron index |

## Vercel deployment

Set server secrets in Project Settings -> Environment Variables. The public
`VITE_TOKEN_CA` value is compiled into the frontend and therefore requires
a redeploy when changed.

The function timeout is 60 seconds. Fable 5.1 uses a 32-second upstream
timeout so the API can still return a controlled JSON error before Vercel
terminates the invocation.

Before production:

1. rotate any API credential that has appeared in chat, logs or screenshots;
2. set `OPENAI_API_KEY` and `HELIUS_API_KEY` for Production;
3. set `VITE_TOKEN_CA` when the project token address is final;
4. build and run the local server;
5. verify `/`, `/docs`, agent requests and holder tabs;
6. deploy only after the checks pass.

## Checks

```bash
python -m unittest discover -s tests
npm --prefix web run build
```

The AI integration can be tested without spending API credit by mocking the
Responses endpoint. A real live-model call should be a deliberate production
smoke test, not part of an automatic build.
