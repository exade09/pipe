import { useCallback, useEffect, useRef, useState } from "react";
import { fetchFeed, fetchHealth } from "./api.js";
import Pulse from "./Pulse.jsx";
import TokenPage from "./TokenPage.jsx";

const MARK = (
  <svg width="22" height="22" viewBox="0 0 512 512" aria-hidden="true">
    <defs>
      <linearGradient id="cu" gradientUnits="userSpaceOnUse" x1="100" y1="80" x2="400" y2="440">
        <stop offset="0" stopColor="#FFD694" />
        <stop offset="0.4" stopColor="#FFC46B" />
        <stop offset="1" stopColor="#E8802A" />
      </linearGradient>
    </defs>
    <path d="M157 148 L285 256 L157 364" fill="none" stroke="url(#cu)" strokeWidth="58" strokeLinecap="round" strokeLinejoin="round" />
    <rect x="329" y="188" width="56" height="176" rx="16" fill="url(#cu)" />
    <circle cx="157" cy="148" r="15" fill="#160B03" />
    <circle cx="157" cy="364" r="15" fill="#160B03" />
  </svg>
);

const FILTERS = [
  ["indexed", "Priced"],
  ["equity", "Equity pair"],
  ["clean", "No flags"],
];

export default function App() {
  const [feed, setFeed] = useState(null);
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");
  const [address, setAddress] = useState(null);
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState({ indexed: false, equity: false, clean: false });
  const [minLiq, setMinLiq] = useState(0);
  const seen = useRef(new Set());
  const [freshest, setFreshest] = useState(null);
  const searchRef = useRef(null);

  const load = useCallback(async (signal) => {
    try {
      const data = await fetchFeed({ limit: 90, minLiquidity: minLiq }, signal);
      setFeed(data);
      setError("");
      // Flash only what we have genuinely not shown before, so a refresh does
      // not light up the whole column.
      const next = data.rows.find((r) => !seen.current.has(r.address));
      data.rows.forEach((r) => seen.current.add(r.address));
      if (next) {
        setFreshest(next.address);
        setTimeout(() => setFreshest(null), 1600);
      }
    } catch (e) {
      if (e.name !== "AbortError") setError(e.message);
    }
  }, [minLiq]);

  useEffect(() => {
    const ctrl = new AbortController();
    load(ctrl.signal);
    fetchHealth(ctrl.signal).then(setHealth).catch(() => {});
    const timer = setInterval(() => load(), 5000);
    return () => { ctrl.abort(); clearInterval(timer); };
  }, [load]);

  useEffect(() => {
    function onKey(e) {
      if (e.target === searchRef.current) {
        if (e.key === "Escape") searchRef.current.blur();
        return;
      }
      if (e.key === "/") { e.preventDefault(); searchRef.current?.focus(); }
      else if (e.key === "Escape" && address) setAddress(null);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [address]);

  const rows = (feed?.rows || []).filter((r) => {
    if (filters.indexed && !r.indexed) return false;
    if (filters.equity && r.native_pair) return false;
    if (filters.clean && r.risk === "risk") return false;
    if (query) {
      const hay = `${r.symbol} ${r.name} ${r.address}`.toLowerCase();
      if (!hay.includes(query.toLowerCase())) return false;
    }
    return true;
  });

  const onChain = feed?.source === "chain";

  return (
    <div className="shell">
      <div className="top">
        <span className="brand">{MARK}<b>PIPE</b></span>
        <span className="grow" />
        <input
          ref={searchRef}
          className="srch"
          placeholder="ticker, name or contract   /"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search"
        />
        <span className="chip"><i />block {feed?.head ?? health?.head ?? "…"}</span>
        {onChain ? (
          <span className="chip warn" title={feed?.note}><i />live window · no index</span>
        ) : (
          <span className="chip"><i />indexed</span>
        )}
      </div>

      <div className="sub">
        <span className="lbl">Filters</span>
        {FILTERS.map(([key, name]) => (
          <button
            key={key}
            className="f"
            aria-pressed={filters[key]}
            onClick={() => setFilters((f) => ({ ...f, [key]: !f[key] }))}
          >
            {name}
          </button>
        ))}
        <span className="sep" />
        <span className="lbl">Min LP</span>
        {[0, 1000, 10000].map((v) => (
          <button key={v} className="f" aria-pressed={minLiq === v} onClick={() => setMinLiq(v)}>
            {v === 0 ? "any" : `$${v / 1000}k`}
          </button>
        ))}
        <span className="sep" />
        <span className="lbl">{rows.length} of {feed?.rows?.length ?? 0} shown</span>
      </div>

      <div className="body">
        {error && <div className="err">{error}</div>}
        {!feed && !error && <div className="loading">reading the chain</div>}
        {feed && !address && <Pulse rows={rows} freshest={freshest} onOpen={setAddress} />}
        {feed && address && <TokenPage address={address} onBack={() => setAddress(null)} />}
      </div>

      <div className="strip">
        <span>chain {feed?.chain_id ?? health?.chain_id ?? "—"}</span>
        <span>rpc {health?.rpc ?? "…"}</span>
        <span>db {health?.database ?? "…"}</span>
        {onChain && <span className="hi">{feed.note}</span>}
        <span style={{ marginLeft: "auto" }}>
          holders replayed from Transfer logs · avatars from token metadata
        </span>
      </div>
    </div>
  );
}
