import Header from "./Header.jsx";

const NAV = [
  ["start", "Start here"],
  ["pulse", "Live pulse"],
  ["workspace", "Token workspace"],
  ["agent", "Fable 5.1 agent"],
  ["bubble", "Bubble map"],
  ["trading", "Trading"],
  ["data", "Data & states"],
  ["shortcuts", "Shortcuts"],
  ["safety", "Safety"],
];

function Code({ children }) {
  return <code className="inline-code">{children}</code>;
}

export default function Docs() {
  return (
    <div className="docs-shell">
      <Header><span className="grow" /><a className="docs-back" href="/">open terminal</a></Header>

      <div className="docs-hero">
        <div>
          <span className="docs-kicker">PIPE / PRODUCT MANUAL</span>
          <h1>Read the market.<br /><span>Keep the evidence.</span></h1>
          <p>
            PIPE is a live Solana token terminal built around explicit evidence:
            what was verified, what raised a flag, and what the data cannot prove.
          </p>
        </div>
        <div className="runtime-card">
          <span className="runtime-pulse" />
          <div>
            <span className="lbl">Agent runtime</span>
            <strong>Fable 5.1</strong>
            <p>Grounded analysis over the token currently open in the terminal.</p>
          </div>
        </div>
      </div>

      <div className="docs-layout">
        <aside className="docs-nav" aria-label="Documentation sections">
          <span className="lbl">Contents</span>
          {NAV.map(([id, label], index) => (
            <a href={`#${id}`} key={id}><i>{String(index + 1).padStart(2, "0")}</i>{label}</a>
          ))}
        </aside>

        <main className="docs-main">
          <section id="start">
            <span className="section-no">01</span>
            <h2>Start here</h2>
            <p>
              The home screen is a continuously refreshed launch pulse. Select a token card to open
              its full workspace; press <Code>A</Code> at any time to show or hide the agent dock.
              PIPE never turns missing data into a zero and never turns an estimate into an on-chain fact.
            </p>
            <div className="docs-grid three">
              <article><span className="mini-icon">01</span><h3>Discover</h3><p>Scan new, late-stage and migrated tokens in parallel.</p></article>
              <article><span className="mini-icon">02</span><h3>Verify</h3><p>Read authorities, liquidity, flow and holder concentration.</p></article>
              <article><span className="mini-icon">03</span><h3>Act</h3><p>Request a route and approve it in your own Solana wallet.</p></article>
            </div>
          </section>

          <section id="pulse">
            <span className="section-no">02</span>
            <h2>Live pulse</h2>
            <p>The board separates tokens by lifecycle instead of mixing unlike markets in one ranking.</p>
            <div className="docs-table">
              <div><b>New</b><span>Newest launch activity first.</span></div>
              <div><b>Final stretch</b><span>Tokens closest to completing their launch curve.</span></div>
              <div><b>Migrated</b><span>Tokens whose launch curve has completed and moved to a market pool.</span></div>
            </div>
            <p>
              Cards expose market cap, liquidity, one-hour volume, transaction direction, age and
              authority status. Copper is product navigation; green and red are reserved for verified
              positive and negative states.
            </p>
          </section>

          <section id="workspace">
            <span className="section-no">03</span>
            <h2>Token workspace</h2>
            <p>
              Opening a token keeps the terminal context while adding chart, read, holders, bubble map,
              security and execution panels. The contract address in the token header is copyable.
            </p>
            <div className="docs-grid two">
              <article><h3>Chart</h3><p>OHLCV candles with timeframe controls, current bar values and an explicit stale-data state.</p></article>
              <article><h3>The read</h3><p>A deterministic summary assembled from checked facts, flags and unknowns. It is not a score.</p></article>
              <article><h3>Holders</h3><p>Largest token accounts resolved to wallet owners so multiple accounts do not masquerade as multiple people.</p></article>
              <article><h3>Security</h3><p>Mint and freeze authority are read from the mint account. Revoked is a floor, not a guarantee.</p></article>
            </div>
          </section>

          <section id="agent">
            <span className="section-no">04</span>
            <h2>Fable 5.1 agent</h2>
            <p>
              The agent in the right dock operates on <strong>Fable 5.1</strong>. When a token is opened,
              it receives a server-curated fact set for that mint: market state, authority checks,
              deterministic findings and holder concentration when available.
            </p>
            <div className="callout">
              <span className="callout-mark">&gt;_</span>
              <div><b>Grounded by construction</b><p>Questions cannot replace the verified fact set. Token metadata is treated as untrusted data, and unavailable evidence stays unavailable.</p></div>
            </div>
            <p>
              Use a suggested prompt or type a question. Replies separate evidence, risks and unknowns,
              include a confidence label, and avoid price predictions or personalized financial advice.
              The API credential exists only in the Vercel server environment and is never sent to the browser.
            </p>
          </section>

          <section id="bubble">
            <span className="section-no">05</span>
            <h2>Holder bubble map</h2>
            <p>
              Each circle represents one resolved wallet. Circle area tracks share of the observed holder
              set; the creator is marked in copper. Hover, focus or select a circle to inspect the wallet,
              rank, share and number of token accounts collapsed into it.
            </p>
            <div className="metric-line">
              <span><b>Top 10</b> concentration</span><span><b>Creator</b> share</span><span><b>Observed</b> wallets</span>
            </div>
            <p className="docs-note">
              The map does not draw wallet-to-wallet links without verified transfer history.
              It describes concentration, not identity, coordination or ownership beyond the resolved accounts.
            </p>
          </section>

          <section id="trading">
            <span className="section-no">06</span>
            <h2>Trading flow</h2>
            <ol className="steps">
              <li><i>1</i><div><b>Connect</b><p>Choose an installed Solana wallet. PIPE never receives a private key.</p></div></li>
              <li><i>2</i><div><b>Review</b><p>Set amount and slippage; confirm expected output, minimum output and price impact.</p></div></li>
              <li><i>3</i><div><b>Approve</b><p>A fresh route is requested immediately before the wallet prompt.</p></div></li>
              <li><i>4</i><div><b>Confirm</b><p>The terminal follows the submitted signature until confirmed, finalized or failed.</p></div></li>
            </ol>
          </section>

          <section id="data">
            <span className="section-no">07</span>
            <h2>Data and honest states</h2>
            <p>
              PIPE combines launch discovery, Solana RPC reads and indexed market data. These systems
              update at different speeds. A token can exist before a pool, a pool can exist before candles,
              and holder analysis can require a keyed RPC.
            </p>
            <div className="state-list">
              <div><span className="state-dot live" /><b>Available</b><p>The upstream answered and the value is shown.</p></div>
              <div><span className="state-dot wait" /><b>Unknown</b><p>The check could not be completed; no substitute value is invented.</p></div>
              <div><span className="state-dot bad" /><b>Flag</b><p>A specific adverse state was read from the source.</p></div>
            </div>
          </section>

          <section id="shortcuts">
            <span className="section-no">08</span>
            <h2>Keyboard shortcuts</h2>
            <div className="shortcut-list">
              <div><kbd>/</kbd><span>Focus token search</span></div>
              <div><kbd>A</kbd><span>Toggle the Fable 5.1 agent</span></div>
              <div><kbd>Esc</kbd><span>Clear focus or return to the pulse</span></div>
              <div><kbd>Enter</kbd><span>Send an agent question from the input</span></div>
            </div>
          </section>

          <section id="safety">
            <span className="section-no">09</span>
            <h2>Safety and limits</h2>
            <p>
              PIPE is an analysis and execution interface, not financial advice. Token markets are volatile,
              indexed data can lag, and the largest-account sample is not a complete holder census.
              Always verify the mint and wallet prompt before approving a transaction.
            </p>
            <p>
              The terminal builds an unsigned transaction; the connected wallet is the only component that
              can sign and send it. Fable 5.1 provides analysis, not guarantees.
            </p>
          </section>
        </main>
      </div>

      <footer className="docs-footer">
        <span>PIPE / Solana intelligence terminal</span>
        <span>Agent runtime: Fable 5.1</span>
        <a href="https://x.com/pipeterminal" target="_blank" rel="noreferrer">@pipeterminal</a>
      </footer>
    </div>
  );
}
