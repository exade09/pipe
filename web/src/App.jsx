import { useCallback, useEffect, useRef, useState } from "react";
import { fetchFeed, fetchHealth } from "./api.js";
import Pulse from "./Pulse.jsx";
import TokenPage from "./TokenPage.jsx";
import Agent from "./Agent.jsx";
import Header from "./Header.jsx";

const FILTERS = [
  ["safe", "Authorities revoked"],
  ["indexed", "Has a pool"],
  ["clean", "No flags"],
];

export default function App() {
  const [feed, setFeed] = useState(null);
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");
  const [mint, setMint] = useState(null);
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState({ safe: false, indexed: false, clean: false });
  const [agentOpen, setAgentOpen] = useState(true);
  const seen = useRef(new Set());
  const [freshest, setFreshest] = useState(null);
  const searchRef = useRef(null);

  const load = useCallback(async (signal) => {
    try {
      const data = await fetchFeed({ limit: 40 }, signal);
      setFeed(data);
      setError("");
      const next = (data.columns.new || []).find((r) => !seen.current.has(r.mint));
      Object.values(data.columns).flat().forEach((r) => seen.current.add(r.mint));
      if (next) {
        setFreshest(next.mint);
        setTimeout(() => setFreshest(null), 1800);
      }
    } catch (e) {
      if (e.name !== "AbortError") setError(e.message);
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    load(ctrl.signal);
    fetchHealth(ctrl.signal).then(setHealth).catch(() => {});
    const timer = setInterval(() => load(), 6000);
    return () => { ctrl.abort(); clearInterval(timer); };
  }, [load]);

  useEffect(() => {
    function onKey(e) {
      if (e.target === searchRef.current) { if (e.key === "Escape") searchRef.current.blur(); return; }
      if (e.key === "/") { e.preventDefault(); searchRef.current?.focus(); }
      else if (e.key.toLowerCase() === "a" && !e.metaKey && !e.ctrlKey) setAgentOpen((v) => !v);
      else if (e.key === "Escape" && mint) setMint(null);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [mint]);

  const filter = (row) => {
    if (filters.safe && (row.can_inflate || row.can_freeze || !row.mint_readable)) return false;
    if (filters.indexed && !row.indexed) return false;
    if (filters.clean && row.risk === "risk") return false;
    if (query) {
      const hay = `${row.symbol} ${row.name} ${row.mint}`.toLowerCase();
      if (!hay.includes(query.toLowerCase())) return false;
    }
    return true;
  };

  const total = feed ? Object.values(feed.columns).flat().length : 0;

  return (
    <div className="shell">
      <Header end={
        <button className="iconbtn" aria-pressed={agentOpen} onClick={() => setAgentOpen((v) => !v)}>
          &gt;_ agent
        </button>
      }>
        <span className="grow" />
        <input
          ref={searchRef} className="srch" placeholder="ticker, name or mint   /"
          value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search"
        />
        <span className="chip"><i />solana</span>
        <span className="chip"><i />slot {health?.slot ?? "…"}</span>
      </Header>

      <div className="sub">
        <span className="lbl">Filters</span>
        {FILTERS.map(([key, name]) => (
          <button key={key} className="f" aria-pressed={filters[key]}
            onClick={() => setFilters((f) => ({ ...f, [key]: !f[key] }))}>
            {name}
          </button>
        ))}
        <span className="sep" />
        <span className="lbl">{total} coins across three columns</span>
      </div>

      <div className={`body${agentOpen ? " with-agent" : ""}`}>
        <div style={{ minWidth: 0, minHeight: 0 }}>
          {error && <div className="err">{error}</div>}
          {!feed && !error && <div className="loading">reading launch activity and mint accounts</div>}
          {feed && !mint && (
            <Pulse columns={feed.columns} freshest={freshest} selected={mint}
              onOpen={setMint} filter={filter} />
          )}
          {feed && mint && <TokenPage mint={mint} onBack={() => setMint(null)} />}
        </div>
        {agentOpen && <Agent mint={mint} onClose={() => setAgentOpen(false)} />}
      </div>

      <div className="strip">
        <span>launches {health?.launches ?? "…"}</span>
        <span>rpc {health?.rpc ?? "…"}</span>
        <span>holders {health?.holders ?? "…"}</span>
        <span>agent {health?.agent ?? "..."}</span>
        <span style={{ marginLeft: "auto" }}>
          launch activity / on-chain authorities / indexed market data
        </span>
      </div>
    </div>
  );
}
