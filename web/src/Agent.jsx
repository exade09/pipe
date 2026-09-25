import { useEffect, useRef, useState } from "react";
import { age, fetchAgentAnalysis, fetchToken, usd } from "./api.js";

const SUGGESTED = [
  "summarize the main risks",
  "what is verified on chain?",
  "read the holder concentration",
  "what changed in the last hour?",
];

const AUTO_ANALYSES = new Map();

function initialAnalysis(mint) {
  if (!AUTO_ANALYSES.has(mint)) {
    const request = fetchAgentAnalysis({
      mint,
      question: "Give me a concise evidence-based overview of this token.",
    }).catch((error) => {
      AUTO_ANALYSES.delete(mint);
      throw error;
    });
    AUTO_ANALYSES.set(mint, request);
  }
  return AUTO_ANALYSES.get(mint);
}

function Analysis({ value }) {
  if (!value) return null;
  return (
    <div className="msg">
      <span className="who">&gt;_</span>
      <div className="bubble-txt agent-read">
        <div className="agent-answer-head">
          <b>{value.headline}</b>
          <span className={`confidence ${value.confidence}`}>{value.confidence}</span>
        </div>
        <p>{value.answer}</p>
        {value.evidence?.length > 0 && (
          <div className="agent-section">
            <span className="lbl">Evidence</span>
            <ul className="lst ok">{value.evidence.map((item, index) => <li key={index}>{item}</li>)}</ul>
          </div>
        )}
        {value.risks?.length > 0 && (
          <div className="agent-section">
            <span className="lbl risk-label">Risks</span>
            <ul className="lst bad">{value.risks.map((item, index) => <li key={index}>{item}</li>)}</ul>
          </div>
        )}
        {value.unknowns?.length > 0 && (
          <div className="agent-section">
            <span className="lbl">Unknowns</span>
            <ul className="lst unk">{value.unknowns.map((item, index) => <li key={index}>{item}</li>)}</ul>
          </div>
        )}
      </div>
    </div>
  );
}

export default function Agent({ mint, onClose }) {
  const [data, setData] = useState(null);
  const [tokenError, setTokenError] = useState("");
  const [analysis, setAnalysis] = useState(null);
  const [agentError, setAgentError] = useState("");
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!mint) {
      setData(null);
      setTokenError("");
      setAnalysis(null);
      setAgentError("");
      setAsked("");
      return undefined;
    }
    let active = true;
    const ctrl = new AbortController();
    setData(null);
    setTokenError("");
    setAnalysis(null);
    setAgentError("");
    setAsked("automatic token read");
    setBusy(true);

    fetchToken(mint, ctrl.signal).then((value) => {
      if (active) setData(value);
    }).catch((error) => {
      if (active && error.name !== "AbortError") setTokenError(error.message);
    });

    initialAnalysis(mint).then((value) => {
      if (active) setAnalysis(value);
    }).catch((error) => {
      if (active) setAgentError(error.message);
    }).finally(() => {
      if (active) setBusy(false);
    });

    return () => {
      active = false;
      ctrl.abort();
    };
  }, [mint]);

  const ask = async (prompt) => {
    const clean = (prompt || question).trim();
    if (!mint || !clean || busy) return;
    setBusy(true);
    setAgentError("");
    setAsked(clean);
    try {
      setAnalysis(await fetchAgentAnalysis({ mint, question: clean }));
      setQuestion("");
    } catch (error) {
      setAgentError(error.message);
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  };

  const read = data?.read;
  const token = data?.token;
  const state = busy ? "reading" : analysis ? "live" : agentError ? "offline" : "ready";

  return (
    <aside className="agent">
      <div className="agent-head">
        <svg width="16" height="16" viewBox="0 0 512 512" aria-hidden="true">
          <path d="M157 148 L285 256 L157 364" fill="none" stroke="#E8802A" strokeWidth="58"
            strokeLinecap="round" strokeLinejoin="round" />
          <rect x="329" y="188" width="56" height="176" rx="16" fill="#E8802A" />
        </svg>
        <span><b>Agent</b><small>Fable 5.1</small></span>
        <span className={`status ${state}`}><i />{state}</span>
        <button className="agent-close" onClick={onClose} aria-label="Close agent">x</button>
      </div>

      <div className="agent-body" aria-live="polite">
        {!mint && (
          <div className="agent-empty">
            <span className="agent-orbit" aria-hidden="true"><i /><i /><i /></span>
            <b>Open a token to begin.</b>
            <p>Fable 5.1 will analyze the verified market, authority and holder facts for the token on screen.</p>
          </div>
        )}

        {mint && tokenError && <p className="err agent-error">{tokenError}</p>}
        {mint && busy && !analysis && (
          <div className="agent-thinking"><span /><span /><span /> grounding the token read</div>
        )}
        {mint && asked && (analysis || agentError) && <p className="agent-question"><span>you</span>{asked}</p>}
        {mint && agentError && <p className="agent-error-box">{agentError}</p>}
        <Analysis value={analysis} />

        {read && token && (
          <div className="msg system">
            <span className="who">i</span>
            <div className="bubble-txt">
              <span className="lbl">Deterministic floor</span>
              {token.symbol} / {token.complete ? "migrated" : `${Math.round(token.progress * 100)}% of curve`} / {age(token.age_minutes)} old.
              Market cap {usd(token.fdv)}{token.indexed ? `, liquidity ${usd(token.liquidity_usd)}` : ", pool data unavailable"}.
              {read.bad.length ? ` ${read.bad.length} verified flag(s).` : " No verified authority flags."}
            </div>
          </div>
        )}
      </div>

      <div className="agent-foot">
        <div className="asks">
          {SUGGESTED.map((prompt) => (
            <button key={prompt} className="ask" disabled={!mint || busy} onClick={() => ask(prompt)}>
              {prompt}
            </button>
          ))}
        </div>
        <form className="agent-input" onSubmit={(event) => { event.preventDefault(); ask(); }}>
          <span className="cu">&gt;</span>
          <input
            ref={inputRef}
            placeholder={mint ? "ask about this token" : "open a token first"}
            value={question}
            maxLength={500}
            disabled={!mint || busy}
            onChange={(event) => setQuestion(event.target.value)}
            aria-label="Ask the Fable 5.1 agent"
          />
          <button className="send" disabled={!mint || !question.trim() || busy} aria-label="Send question">
            {busy ? "..." : "enter"}
          </button>
        </form>
        <p className="agent-note">Evidence-based analysis, not financial advice. Missing facts stay unknown.</p>
      </div>
    </aside>
  );
}
