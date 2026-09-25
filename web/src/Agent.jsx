import { useEffect, useState } from "react";
import { fetchToken, usd, age } from "./api.js";

/*
  The agent dock.

  It is not connected yet, and this panel does not pretend otherwise — but it
  is also not an empty box waiting for a backend. Everything it shows is real:
  the read is already computed server-side from facts pulled off the mint, the
  curve and the pool, so the dock surfaces it in the shape the agent will
  eventually speak in.

  What is honestly disabled is the part that needs a model: the free-form
  question box. It is dimmed, it says why, and the suggested questions are
  shown as what will be answerable rather than as working buttons. When the
  model lands, the same panel gains a reply and nothing about its layout has
  to move.
*/

const SUGGESTED = [
  "who is holding this",
  "has the creator sold",
  "what happened in the last hour",
  "compare this to the last coin i opened",
];

export default function Agent({ mint, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!mint) { setData(null); setError(""); return; }
    const ctrl = new AbortController();
    setData(null); setError("");
    fetchToken(mint, ctrl.signal).then(setData).catch((e) => {
      if (e.name !== "AbortError") setError(e.message);
    });
    return () => ctrl.abort();
  }, [mint]);

  const read = data?.read;
  const t = data?.token;

  return (
    <aside className="agent">
      <div className="agent-head">
        <svg width="16" height="16" viewBox="0 0 512 512" aria-hidden="true">
          <path d="M157 148 L285 256 L157 364" fill="none" stroke="#E8802A" strokeWidth="58"
            strokeLinecap="round" strokeLinejoin="round" />
          <rect x="329" y="188" width="56" height="176" rx="16" fill="#E8802A" />
        </svg>
        <b>Agent</b>
        <span className="status"><i />not connected</span>
        <button className="agent-close" onClick={onClose} aria-label="Close agent">×</button>
      </div>

      <div className="agent-body">
        {!mint && (
          <p className="agent-empty">
            Open a coin and the read appears here. Once the model is connected this becomes a
            conversation about whatever is on screen — for now it shows what has already been
            worked out from the chain.
          </p>
        )}

        {mint && error && <p className="err" style={{ padding: 0 }}>{error}</p>}
        {mint && !data && !error && <p className="loading" style={{ padding: 0 }}>reading</p>}

        {read && t && (
          <>
            <div className="msg">
              <span className="who">›_</span>
              <div className="bubble-txt">
                <span className="lbl">{t.symbol} · {t.complete ? "migrated" : `${Math.round(t.progress * 100)}% of curve`} · {age(t.age_minutes)} old</span>
                {read.verdict}
              </div>
            </div>

            <div className="msg">
              <span className="who">›_</span>
              <div className="bubble-txt agent-facts">
                <div>
                  <span className="lbl">Checked</span>
                  <ul className="lst ok">{read.ok.map((x, i) => <li key={i}>{x}</li>)}</ul>
                </div>
                {read.bad.length > 0 && (
                  <div>
                    <span className="lbl" style={{ color: "#E05340" }}>Flags</span>
                    <ul className="lst bad">{read.bad.map((x, i) => <li key={i}>{x}</li>)}</ul>
                  </div>
                )}
                <div>
                  <span className="lbl">Could not check</span>
                  <ul className="lst unk">{read.unk.map((x, i) => <li key={i}>{x}</li>)}</ul>
                </div>
              </div>
            </div>

            <div className="msg system">
              <span className="who" style={{ color: "#4A443E" }}>·</span>
              <div className="bubble-txt">
                Market cap {usd(t.fdv)}
                {t.indexed ? `, liquidity ${usd(t.liquidity_usd)}` : ", no pool indexed yet"}.
                Everything above is a fact with something behind it, which is the only
                thing the model will be allowed to build on.
              </div>
            </div>
          </>
        )}
      </div>

      <div className="agent-foot">
        <div className="asks">
          {SUGGESTED.map((q) => (
            <button key={q} className="ask" disabled title="Not connected yet">{q}</button>
          ))}
        </div>
        <div className="agent-input">
          <span className="cu">›</span>
          <input placeholder="ask about this coin" disabled aria-label="Ask the agent" />
          <span className="send">⏎</span>
        </div>
        <p className="agent-note">
          The question box is disabled because no model is wired to it yet. The read above is
          live, and when the model lands it answers out of exactly those facts — never around
          them.
        </p>
      </div>
    </aside>
  );
}
