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
  const [src, setSrc] = useState(token.image_url || fallbackAvatar(token.mint));
  return (
    <img className="av" width={size} height={size} src={src} alt="" referrerPolicy="no-referrer"
      onError={() => setSrc(fallbackAvatar(token.mint))} />
  );
}

function Change({ value }) {
  const n = Number(value) || 0;
  return <span className={n >= 0 ? "up" : "down"}>{n >= 0 ? "+" : ""}{n.toFixed(1)}%</span>;
}

export default function TokenPage({ mint, onBack }) {
  const [data, setData] = useState(null);
  const [holders, setHolders] = useState(null);
  const [holdersError, setHoldersError] = useState("");
  const [tab, setTab] = useState("read");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const ctrl = new AbortController();
    setData(null); setHolders(null); setHoldersError(""); setError("");
    fetchToken(mint, ctrl.signal).then(setData).catch((e) => {
      if (e.name !== "AbortError") setError(e.message);
    });
    return () => ctrl.abort();
  }, [mint]);

  // Holders are the call no free endpoint serves, so they are fetched only
  // when a tab that needs them is opened — and the refusal is shown as the
  // answer it is, not swallowed into an empty chart.
  useEffect(() => {
    if (holders || holdersError || (tab !== "holders" && tab !== "bubble")) return;
    const ctrl = new AbortController();
    fetchHolders(mint, ctrl.signal).then(setHolders).catch((e) => {
      if (e.name !== "AbortError") setHoldersError(e.message);
    });
    return () => ctrl.abort();
  }, [tab, mint, holders, holdersError]);

  if (error) return <div className="err">{error}</div>;
  if (!data) return <div className="loading">reading the chain</div>;

  const t = data.token;
  const read = data.read || { verdict: "", ok: [], bad: [], unk: [], risk: "watch" };
  const pct = Math.round((Number(t.progress) || 0) * 100);

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
              {t.name || "—"} · {t.complete ? "migrated" : `${pct}% of curve`} · {age(t.age_minutes)} old
            </span>
          </span>
          <span className="ca" onClick={() => {
            navigator.clipboard?.writeText(t.mint).catch(() => {});
            setCopied(true); setTimeout(() => setCopied(false), 1400);
          }}>
            {copied ? "copied" : `${short(t.mint)} ⧉`}
          </span>
          <span className="px">{usd(t.fdv)} {t.indexed && <Change value={t.change_h1} />}</span>
        </div>

        <div className="stats">
          <div><div className="lbl">Liquidity</div><div className="v">{t.indexed ? usd(t.liquidity_usd) : "—"}</div></div>
          <div><div className="lbl">Volume 1h</div><div className="v">{t.indexed ? usd(t.volume_h1) : "—"}</div></div>
          <div><div className="lbl">Buys / sells</div><div className="v">{t.buys_h1 || 0} / {t.sells_h1 || 0}</div></div>
          <div><div className="lbl">Curve</div><div className="v">{t.complete ? "done" : `${pct}%`}</div></div>
          <div>
            <div className="lbl">Mint authority</div>
            <div className={`v ${t.can_inflate ? "down" : "up"}`}>{t.can_inflate ? "live" : "revoked"}</div>
          </div>
          <div>
            <div className="lbl">Freeze authority</div>
            <div className={`v ${t.can_freeze ? "down" : "up"}`}>{t.can_freeze ? "live" : "revoked"}</div>
          </div>
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
                There is no score. A coin with four ticks and three unknowns is a different object
                from one with seven ticks, and a number out of a hundred hides that difference —
                which is the whole reason every other scanner prints one.
              </p>
            </>
          )}

          {(tab === "holders" || tab === "bubble") && holdersError && (
            <div>
              <p className="lbl" style={{ color: "#FFC46B" }}>Not available on this deployment</p>
              <p className="verdict" style={{ marginTop: 10 }}>{holdersError}</p>
              <p className="note">
                Everything else on this page is read without a key. This one call is the exception,
                and it is shown as a refusal rather than as a coin with no holders.
              </p>
            </div>
          )}

          {tab === "holders" && !holdersError && (
            !holders ? <div className="loading">reading the largest accounts</div> : (
              <>
                <div className="distbar">
                  {holders.holders.slice(0, 10).map((h, i) => (
                    <i key={i} style={{ width: `${h.share}%`, background: `hsl(${24 + i * 7},60%,${48 - i * 2}%)` }} />
                  ))}
                  <i style={{ flex: 1, background: "#1E1A16" }} />
                </div>
                <div className="tbl">
                  <table>
                    <thead><tr><th>Wallet</th><th>Share</th><th>Accounts</th><th>Note</th></tr></thead>
                    <tbody>
                      {holders.holders.map((h) => (
                        <tr key={h.owner || h.account}>
                          <td className="dim">{short(h.owner || h.account)}</td>
                          <td className={h.share > 10 ? "down" : ""}>{h.share.toFixed(2)}%</td>
                          <td className="dim">{h.accounts}</td>
                          <td className={h.is_creator ? "cu" : "dim"}>{h.is_creator ? "creator" : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="note">{holders.note}</p>
              </>
            )
          )}

          {tab === "bubble" && !holdersError && (
            !holders ? <div className="loading">mapping holders</div> : <BubbleMap data={holders} />
          )}

          {tab === "security" && (
            <>
              <div className="cols2">
                <div>
                  <span className="lbl">Read off the chain</span>
                  <ul className="lst ok">{read.ok.map((x, i) => <li key={i}>{x}</li>)}</ul>
                </div>
                <div>
                  {read.bad.length > 0 && (
                    <>
                      <span className="lbl" style={{ color: "#E05340" }}>Flags</span>
                      <ul className="lst bad">{read.bad.map((x, i) => <li key={i}>{x}</li>)}</ul>
                    </>
                  )}
                  <span className="lbl" style={{ display: "block", marginTop: read.bad.length ? 14 : 0 }}>Open</span>
                  <ul className="lst unk">{read.unk.map((x, i) => <li key={i}>{x}</li>)}</ul>
                </div>
              </div>
              <p className="note">
                Mint authority and freeze authority are read straight off the mint account. Revoked
                means the supply cannot grow and a balance cannot be frozen in the wallet holding
                it. That is the floor, not a verdict.
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
            Reads are live. Signing is not connected — no wallet, no approvals, nothing can leave
            an account from this screen.
          </p>
        </div>

        <div className="blk">
          <span className="lbl">On chain</span>
          <div className="kv" style={{ marginTop: 8 }}>
            <span className="k">mint</span><span>{short(t.mint)}</span>
            <span className="k">creator</span><span>{short(t.creator)}</span>
            <span className="k">curve</span><span>{short(t.bonding_curve)}</span>
            {t.pool_address && (<><span className="k">pool</span><span>{short(t.pool_address)}</span></>)}
            <span className="k">decimals</span><span>{t.decimals}</span>
            <span className="k">quote</span><span>{t.quote_symbol}</span>
            <span className="k">replies</span><span>{t.reply_count}</span>
          </div>
        </div>
      </aside>
    </div>
  );
}
