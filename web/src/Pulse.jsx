import { useState } from "react";
import { usd, age, fallbackAvatar } from "./api.js";

/*
  Three columns, and on this chain all three rest on a real field rather than
  on a proxy for one:

    New            newest by creation time
    Final stretch  sorted by how much the curve has actually taken
    Migrated       pump.fun's own `complete` flag, not a guess from age

  A row is a card. The pills under the name are the facts that decide whether
  it is worth opening at all — the two mint authorities first, because a coin
  that can still be inflated or frozen is settled before liquidity or holders
  are worth a glance.

  The bar is curve progress and only fills for a coin that has migrated. A
  curve sitting past the threshold but still open is capped short on purpose:
  a full bar next to something that has not graduated is a lie the eye
  believes before the label corrects it.
*/

function Avatar({ row }) {
  const [src, setSrc] = useState(row.image_url || fallbackAvatar(row.mint));
  return (
    <img
      className="av" width="42" height="42" src={src} alt=""
      loading="lazy" referrerPolicy="no-referrer"
      onError={() => setSrc(fallbackAvatar(row.mint))}
    />
  );
}

function Pills({ row }) {
  const pills = [];

  if (!row.mint_readable) {
    pills.push(["mint ?", "warn"]);
  } else {
    pills.push(row.can_inflate ? ["mint open", "bad"] : ["mint revoked", "good"]);
    pills.push(row.can_freeze ? ["freeze on", "bad"] : ["freeze revoked", "good"]);
  }

  if (row.indexed) {
    const buys = Number(row.buys_h1) || 0;
    const sells = Number(row.sells_h1) || 0;
    if (buys + sells > 0) pills.push([`${buys}b / ${sells}s`, buys >= sells ? "good" : ""]);
  } else {
    pills.push(["no pool", ""]);
  }

  if (row.reply_count > 0) pills.push([`${row.reply_count} replies`, ""]);

  return (
    <span className="pills">
      {pills.map(([text, kind], i) => (
        <span key={i} className={`pill ${kind}`}>{text}</span>
      ))}
    </span>
  );
}

function Row({ row, fresh, selected, onOpen }) {
  const change = Number(row.change_h1) || 0;
  const pct = Math.round((Number(row.progress) || 0) * 100);
  return (
    <button
      className={`row${fresh ? " fresh" : ""}${selected ? " sel" : ""}`}
      onClick={() => onOpen(row.mint)}
    >
      <Avatar row={row} />
      <span>
        <span className="l1">
          <span className="s">{row.symbol || "?"}</span>
          <span className={`flag ${row.risk || "watch"}`}>
            {row.risk === "risk" ? "flagged" : row.risk === "ok" ? "clean" : "watch"}
          </span>
          <span className="nm">{row.name || ""}</span>
          <span className="age">{age(row.age_minutes)}</span>
        </span>

        <span className="l2">
          <span>MC <b>{usd(row.fdv)}</b></span>
          {row.indexed && (
            <>
              <span>LP <b>{usd(row.liquidity_usd)}</b></span>
              <span>V1h <b>{usd(row.volume_h1)}</b></span>
              <span className={change >= 0 ? "up" : "down"}>
                {change >= 0 ? "+" : ""}{change.toFixed(1)}%
              </span>
            </>
          )}
        </span>

        <Pills row={row} />

        <span className="l3">
          <span className={`bar${row.complete ? " done" : ""}`}><i style={{ width: `${pct}%` }} /></span>
          <span className="dim tiny">{row.complete ? "migrated" : `${pct}%`}</span>
        </span>
      </span>
    </button>
  );
}

function Column({ title, why, rows, freshest, selected, onOpen }) {
  return (
    <div className="col">
      <div className="colhead">
        <b>{title}</b>
        <span className="why">{why}</span>
        <span className="n">{rows.length}</span>
      </div>
      <div className="colbody">
        {rows.length === 0 ? (
          <p className="empty">Nothing here with the current filters.</p>
        ) : (
          rows.map((row) => (
            <Row
              key={row.mint} row={row}
              fresh={row.mint === freshest}
              selected={row.mint === selected}
              onOpen={onOpen}
            />
          ))
        )}
      </div>
    </div>
  );
}

export default function Pulse({ columns, freshest, selected, onOpen, filter }) {
  const pick = (list) => (list || []).filter(filter);
  return (
    <div className="pulse">
      <Column title="New" why="newest first" rows={pick(columns.new)}
        freshest={freshest} selected={selected} onOpen={onOpen} />
      <Column title="Final stretch" why="closest to migration" rows={pick(columns.stretch)}
        selected={selected} onOpen={onOpen} />
      <Column title="Migrated" why="curve finished" rows={pick(columns.migrated)}
        selected={selected} onOpen={onOpen} />
    </div>
  );
}
