import { useEffect, useState } from "react";
import { fetchToken, fetchHolders, usd, age, short, fallbackAvatar } from "./api.js";
import BubbleMap from "./BubbleMap.jsx";

const TABS = [
  ["read", "The read"],
  ["holders", "Holders"],
  ["bubble", "Bubble map"],
  ["security", "Security"],
];

function Avatar({ token, size = 30 }) {
  const [src, setSrc] = useState(token.image_url || fallbackAvatar(token.address));
  return (
    <img
      className="av" width={size} height={size} src={src} alt=""
      onError={() => setSrc(fallbackAvatar(token.address))}
    />
  );
}

function Change({ value }) {
  const n = Number(value) || 0;
  return <span className={n >= 0 ? "up" : "down"}>{n >= 0 ? "+" : ""}{n.toFixed(1)}%</span>;
}

export default function TokenPage({ address, onBack }) {
  const [data, setData] = useState(null);
  const [holders, setHolders] = useState(null);
  const [tab, setTab] = useState("read");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const ctrl = new AbortController();
    setData(null);
    setHolders(null);
    setError("");
    fetchToken(address, ctrl.signal).then(setData).catch((e) => {
      if (e.name !== "AbortError") setError(e.message);
    });
    return () => ctrl.abort();
  }, [address]);

  // Holders are the expensive read, so they are only fetched when the tab that
  // needs them is opened — and then reused for both of those tabs.
  useEffect(() => {
    if (holders || (tab !== "holders" && tab !== "bubble")) return;
    const ctrl = new AbortController();
    fetchHolders(address, ctrl.signal).then(setHolders).catch(() => {});
    return () => ctrl.abort();
  }, [tab, address, holders]);

  if (error) return <div className="err">{error}</div>;
  if (!data) return <div className="loading">reading the chain</div>;

  const t = data.token;
  const read = data.read || { verdict: "", ok: [], bad: [], unk: [], risk: "watch" };
  const snapshot = holders || data.holders;

  return (
    <div className="token">
      <div className="tmain">
        <div className="thead">
          <button className="back" onClick={onBack}>← pulse</button>
          <Avatar token={t} />
          <span>
            <b style={{ fontSize: 15 }}>{t.symbol}</b>{" "}
            <span className={`flag ${read.risk}`}>
              {read.risk === "risk" ? "flagged" : read.risk === "watch" ? "watch" : "clean"}
            </span>
            <br />
            <span className="dim" style={{ fontSize: 10.5 }}>
              {t.name || "—"} · paired to {t.quote_symbol || (t.native_pair ? "ETH" : "?")} · {age(t.age_minutes)} old
            </span>
          </span>
          <span
            className="ca"
            onClick={() => {
              navigator.clipboard?.writeText(t.address).catch(() => {});
              setCopied(true);
              setTimeout(() => setCopied(false), 1400);
            }}
          >
            {copied ? "copied" : `${short(t.address)} ⧉`}
          </span>
          <span className="px">
            {t.indexed ? usd(t.fdv) : <span className="dim">not priced yet</span>}{" "}
            {t.indexed && <Change value={t.change_h1} />}
          </span>
        </div>

        <div className="stats">
          <div><div className="lbl">Liquidity</div><div className="v">{t.indexed ? usd(t.liquidity_usd) : "—"}</div></div>
          <div><div className="lbl">Volume 1h</div><div className="v">{t.indexed ? usd(t.volume_h1) : "—"}</div></div>
          <div><div className="lbl">Buys / sells 1h</div><div className="v">{t.buys_h1 || 0} / {t.sells_h1 || 0}</div></div>
          <div><div className="lbl">Holders</div><div className="v">{snapshot?.counted ?? t.holders_counted ?? "—"}</div></div>
          <div>
            <div className="lbl">Top 10</div>
            <div className={`v ${(snapshot?.top10_share ?? 0) > 40 ? "down" : ""}`}>
              {snapshot ? `${snapshot.top10_share.toFixed(1)}%` : "—"}
            </div>
          </div>
          <div><div className="lbl">Launch block</div><div className="v">{t.launch_block}</div></div>
        </div>

        <div className="tabs" role="tablist">
          {TABS.map(([key, name]) => (
            <button key={key} className="tb" role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>
              {name}
            </button>
          ))}
        </div>

        <div className="pane">
          {tab === "read" && (
            <>
              <p className="lbl">The read · assembled from the facts below, never from a score</p>
              <p className="verdict">{read.verdict}</p>
              <div className="cols2">
                <div>
                  <span className="lbl">Checked on chain</span>
                  <ul className="lst ok">{read.ok.map((x, i) => <li key={i}>{x}</li>)}</ul>
                </div>
                <div>
                  {read.bad.length > 0 && (
                    <>
                      <span className="lbl" style={{ color: "#E05340" }}>Flags</span>
                      <ul className="lst bad">{read.bad.map((x, i) => <li key={i}>{x}</li>)}</ul>
                    </>
                  )}
                  <span className="lbl" style={{ display: "block", marginTop: read.bad.length ? 14 : 0 }}>
                    Could not be checked
                  </span>
                  <ul className="lst unk">{read.unk.map((x, i) => <li key={i}>{x}</li>)}</ul>
                </div>
              </div>
              <p className="note">
                There is no score. A token with four ticks and three unknowns is a different
                object from one with seven ticks, and a number out of a hundred hides that
                difference — which is the whole reason every other scanner prints one.
              </p>
            </>
          )}

          {tab === "holders" && (
            !snapshot ? <div className="loading">replaying transfer logs</div> : (
              <>
                <div className="distbar">
                  {snapshot.holders.slice(0, 10).map((h, i) => (
                    <i key={i} style={{ width: `${h.share}%`, background: `hsl(${24 + i * 7},60%,${48 - i * 2}%)` }} />
                  ))}
                  <i style={{ flex: 1, background: "#1E1A16" }} />
                </div>
                <div className="tbl">
                  <table>
                    <thead>
                      <tr><th>Wallet</th><th>Share</th><th>First seen</th><th>Cluster</th><th>Note</th></tr>
                    </thead>
                    <tbody>
                      {snapshot.holders.slice(0, 25).map((h) => (
                        <tr key={h.address}>
                          <td className="dim">{short(h.address)}</td>
                          <td className={h.share > 10 ? "down" : ""}>{h.share.toFixed(2)}%</td>
                          <td className="dim">block {h.first_block}</td>
                          <td className="dim">{h.cluster >= 0 ? `#${h.cluster + 1}` : "—"}</td>
                          <td className={h.is_deployer ? "cu" : "dim"}>{h.is_deployer ? "deployer" : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="note">
                  The curve is excluded. It holds every token nobody has bought yet, and counting
                  it as a holder makes every new launch look like a 96% rug.
                </p>
              </>
            )
          )}

          {tab === "bubble" && (
            !snapshot ? <div className="loading">mapping holders</div> : <BubbleMap data={snapshot} />
          )}

          {tab === "security" && (
            <>
              <div className="cols2">
                <div>
                  <span className="lbl">Read off the chain</span>
                  <ul className="lst ok">{read.ok.map((x, i) => <li key={i}>{x}</li>)}</ul>
                </div>
                <div>
                  <span className="lbl">Open</span>
                  <ul className="lst unk">{read.unk.map((x, i) => <li key={i}>{x}</li>)}</ul>
                  {read.bad.length > 0 && (
                    <>
                      <span className="lbl" style={{ display: "block", marginTop: 14, color: "#E05340" }}>Flags</span>
                      <ul className="lst bad">{read.bad.map((x, i) => <li key={i}>{x}</li>)}</ul>
                    </>
                  )}
                </div>
              </div>
              <p className="note">
                Every line is a fact with a transaction behind it. Passing all of them is not a
                recommendation — it means the checkable things checked out.
              </p>
            </>
          )}
        </div>
      </div>

      <aside className="rail">
        <div className="blk">
          <span className="lbl">Order</span>
          <div className="presets" style={{ marginTop: 8 }}>
            <button aria-pressed="false" disabled>0.1</button>
            <button aria-pressed="true" disabled>0.5</button>
            <button aria-pressed="false" disabled>1.0</button>
          </div>
          <button className="go" disabled>Trading not wired yet</button>
          <p className="fine">
            Reads are live. Signing is not connected — no wallet, no approvals, nothing can
            leave an account from this screen.
          </p>
        </div>

        <div className="blk">
          <span className="lbl">On chain</span>
          <div className="kv" style={{ marginTop: 8 }}>
            <span className="k">token</span><span>{short(t.address)}</span>
            <span className="k">curve</span><span>{short(t.curve)}</span>
            <span className="k">deployer</span><span>{short(t.deployer)}</span>
            <span className="k">pair</span><span>{t.native_pair ? "native ETH" : short(t.pair_token)}</span>
            <span className="k">decimals</span><span>{t.decimals}</span>
            <span className="k">launch</span><span>block {t.launch_block}</span>
          </div>
        </div>

        {snapshot?.clusters?.length > 0 && (
          <div className="blk">
            <span className="lbl">Clusters</span>
            <div className="kv" style={{ marginTop: 8 }}>
              {snapshot.clusters.slice(0, 5).map((c) => (
                <span key={c.index} style={{ display: "contents" }}>
                  <span className="k">#{c.index + 1} · {c.wallets} wallets</span>
                  <span>{c.share}%</span>
                </span>
              ))}
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
