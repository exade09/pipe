import { useCallback, useEffect, useRef, useState } from "react";
import {
  LAMPORTS,
  amountText,
  buildSwap,
  fetchQuote,
  fetchTx,
  fetchWallet,
  fromBase,
  priceText,
  toBase,
} from "./api.js";
import { connect, disconnect, installed, readableError, signAndSend } from "./wallet.js";

/*
  The order panel.

  Everything else in this terminal reads the chain. This is the one place that
  lets the reader act on it, and the arrangement of that act is deliberate:

    · the backend prices the route and builds an unsigned transaction
    · the browser hands that transaction to the reader's own wallet
    · the wallet is the only thing that signs, and the only thing that sends

  No key is held anywhere in this product, and the server has no way to submit
  what it built. That is why the panel can be this direct about the rest.

  Three numbers are always on screen before the button can be pressed: what
  you receive, the least you receive if the whole slippage tolerance is used,
  and the price impact. A swap panel that shows only the first is showing a
  price it cannot promise. The quote is re-taken every eight seconds and again
  the moment before signing, because a quote on a meme coin goes stale in
  about that long.
*/

const BUY_PRESETS = [0.1, 0.25, 0.5, 1];
const SELL_PRESETS = [25, 50, 75, 100];
const SLIPPAGES = [50, 100, 300, 1000];

function Field({ label, children }) {
  return (
    <div className="fld">
      <span className="lbl">{label}</span>
      {children}
    </div>
  );
}

export default function Trade({ token }) {
  const mint = token.mint;
  const decimals = Number(token.decimals) || 6;

  const [side, setSide] = useState("buy");
  const [amount, setAmount] = useState("0.1");
  const [slippage, setSlippage] = useState(100);
  const [wallet, setWallet] = useState(null);
  const [balances, setBalances] = useState(null);
  const [quote, setQuote] = useState(null);
  const [quoting, setQuoting] = useState(false);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [receipt, setReceipt] = useState(null);
  const [options, setOptions] = useState(installed);

  // Wallet extensions inject their provider a moment after the page loads, so
  // a list taken at first render can be empty in a browser that has three.
  useEffect(() => {
    const timers = [300, 1200].map((ms) => setTimeout(() => setOptions(installed()), ms));
    return () => timers.forEach(clearTimeout);
  }, []);

  /* ------------------------------------------------------------- wallet */

  const onConnect = async (id) => {
    setError("");
    try {
      setWallet(await connect(id));
    } catch (e) {
      setError(readableError(e));
    }
  };

  const onDisconnect = async () => {
    if (wallet) await disconnect(wallet.id);
    setWallet(null);
    setBalances(null);
  };

  useEffect(() => {
    if (!wallet) return undefined;
    const ctrl = new AbortController();
    const read = () =>
      fetchWallet(wallet.address, mint, ctrl.signal)
        .then(setBalances)
        .catch(() => {});
    read();
    const timer = setInterval(read, 15000);
    return () => {
      ctrl.abort();
      clearInterval(timer);
    };
  }, [wallet, mint]);

  /* -------------------------------------------------------------- quote */

  const held = balances?.token_ui || 0;
  const baseAmount =
    side === "buy"
      ? toBase(amount, 9)
      : Math.min(toBase(amount, decimals), Number(balances?.token?.amount) || Infinity);

  const takeQuote = useCallback(
    async (signal) => {
      if (!baseAmount) {
        setQuote(null);
        return null;
      }
      setQuoting(true);
      try {
        const next = await fetchQuote({ side, mint, amount: baseAmount, slippage_bps: slippage }, signal);
        setQuote(next);
        setError("");
        return next;
      } catch (e) {
        if (e.name !== "AbortError") {
          setQuote(null);
          setError(e.message);
        }
        return null;
      } finally {
        setQuoting(false);
      }
    },
    [baseAmount, side, mint, slippage],
  );

  useEffect(() => {
    const ctrl = new AbortController();
    const debounce = setTimeout(() => takeQuote(ctrl.signal), 320);
    const timer = setInterval(() => takeQuote(), 8000);
    return () => {
      ctrl.abort();
      clearTimeout(debounce);
      clearInterval(timer);
    };
  }, [takeQuote]);

  /* --------------------------------------------------------------- send */

  const onSubmit = async () => {
    if (!wallet || !baseAmount) return;
    setSending(true);
    setError("");
    setReceipt(null);
    try {
      // A quote taken eight seconds ago is a different price. The one that
      // gets signed is taken here, immediately before signing.
      const fresh = (await takeQuote()) || quote;
      if (!fresh) throw new Error("No live quote to sign.");
      const built = await buildSwap({ owner: wallet.address, quote: fresh.quote, priority_lamports: 1_500_000 });
      const signature = await signAndSend(wallet.id, built.transaction);
      setReceipt({ signature, status: "pending" });

      for (let i = 0; i < 24; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        try {
          const status = await fetchTx(signature);
          setReceipt({ signature, ...status });
          if (status.status === "failed" || status.status === "confirmed" || status.status === "finalized") break;
        } catch {
          /* the status endpoint being briefly unhappy is not the trade failing */
        }
      }
    } catch (e) {
      setError(readableError(e));
    } finally {
      setSending(false);
    }
  };

  /* --------------------------------------------------------------- view */

  const outUi = quote ? fromBase(quote.out_amount, side === "buy" ? decimals : 9) : 0;
  const minUi = quote ? fromBase(quote.min_out_amount, side === "buy" ? decimals : 9) : 0;
  const impact = quote ? Number(quote.price_impact_pct) || 0 : 0;
  const solBalance = balances?.sol || 0;
  const overSpend = side === "buy" && wallet && Number(amount) > solBalance;
  const ready = !!wallet && !!quote && !!baseAmount && !sending && !overSpend;

  return (
    <div className="trade">
      <div className="sides">
        <button className="sd buy" aria-pressed={side === "buy"} onClick={() => { setSide("buy"); setAmount("0.1"); }}>
          Buy
        </button>
        <button className="sd sell" aria-pressed={side === "sell"} onClick={() => { setSide("sell"); setAmount("50"); }}>
          Sell
        </button>
      </div>

      <Field label={side === "buy" ? "Amount in SOL" : `Amount in ${token.symbol}`}>
        <div className="amt">
          <input
            inputMode="decimal" value={amount} aria-label="Amount"
            onChange={(e) => setAmount(e.target.value.replace(/[^0-9.]/g, ""))}
          />
          <span className="unit">{side === "buy" ? "SOL" : token.symbol}</span>
        </div>
      </Field>

      <div className="presets">
        {(side === "buy" ? BUY_PRESETS : SELL_PRESETS).map((p) => (
          <button
            key={p}
            onClick={() => setAmount(side === "buy" ? String(p) : String(+((held * p) / 100).toFixed(6)))}
            title={side === "buy" ? `${p} SOL` : `${p}% of what you hold`}
          >
            {side === "buy" ? p : `${p}%`}
          </button>
        ))}
      </div>

      <div className="slip">
        <span className="lbl">Slippage</span>
        {SLIPPAGES.map((bps) => (
          <button key={bps} aria-pressed={slippage === bps} onClick={() => setSlippage(bps)}>
            {bps / 100}%
          </button>
        ))}
      </div>

      <div className="quote">
        {quoting && !quote && <span className="dim tiny">pricing the route</span>}
        {quote && (
          <>
            <div className="qrow">
              <span>You receive</span>
              <b>{amountText(outUi)} {side === "buy" ? token.symbol : "SOL"}</b>
            </div>
            <div className="qrow">
              <span>At least</span>
              <b>{amountText(minUi)} {side === "buy" ? token.symbol : "SOL"}</b>
            </div>
            <div className="qrow">
              <span>Price impact</span>
              <b className={impact > 5 ? "down" : impact > 1 ? "hi" : "up"}>{impact.toFixed(2)}%</b>
            </div>
            <div className="qrow">
              <span>Route</span>
              <b>{quote.route.join(" → ") || "direct"}</b>
            </div>
          </>
        )}
        {!quote && !quoting && !error && <span className="dim tiny">enter an amount for a live quote</span>}
      </div>

      {wallet ? (
        <>
          <div className="bal">
            <span>{balances ? `${solBalance.toFixed(4)} SOL` : "reading balance"}</span>
            <span className="grow" />
            <span>{balances?.token ? `${amountText(held)} ${token.symbol}` : ""}</span>
          </div>
          <button className="exec" disabled={!ready} onClick={onSubmit}>
            {sending
              ? "waiting for your wallet"
              : overSpend
                ? "more SOL than the wallet holds"
                : `${side === "buy" ? "Buy" : "Sell"} ${token.symbol}`}
          </button>
          <button className="unlink" onClick={onDisconnect}>
            {wallet.address.slice(0, 4)}…{wallet.address.slice(-4)} · disconnect
          </button>
        </>
      ) : (
        <div className="connect">
          {options.length === 0 ? (
            <p className="fine">
              No Solana wallet in this browser. Phantom, Solflare and Backpack all work here; install
              one and this panel connects to it.
            </p>
          ) : (
            options.map((w) => (
              <button key={w.id} className="exec" onClick={() => onConnect(w.id)}>
                Connect {w.label}
              </button>
            ))
          )}
        </div>
      )}

      {error && <p className="fine down">{error}</p>}

      {receipt && (
        <p className="fine">
          <span className={receipt.status === "failed" ? "down" : receipt.status === "pending" ? "hi" : "up"}>
            {receipt.status === "pending" ? "sent, waiting for confirmation" : receipt.status}
          </span>
          {" · "}
          <a href={`https://solscan.io/tx/${receipt.signature}`} target="_blank" rel="noreferrer" className="cu">
            {receipt.signature.slice(0, 8)}…
          </a>
          {receipt.error ? ` · ${receipt.error}` : ""}
        </p>
      )}

      <p className="fine">
        Your wallet signs and sends. This terminal holds no keys and cannot submit a transaction —
        it only prices the route and builds one for you to approve.
      </p>

      <div className="mkt">
        <div className="kv">
          <span className="k">price</span>
          <span>{priceText(token.price_usd)}</span>
          <span className="k">liquidity</span>
          <span>{token.indexed ? `$${Math.round(token.liquidity_usd).toLocaleString()}` : "no pool"}</span>
          <span className="k">1 SOL buys</span>
          <span>
            {quote && side === "buy" && Number(amount) > 0
              ? `${amountText(outUi / Number(amount))} ${token.symbol}`
              : "—"}
          </span>
          <span className="k">lamports</span>
          <span>{balances ? balances.lamports.toLocaleString() : "—"}</span>
        </div>
      </div>
    </div>
  );
}

export { LAMPORTS };
