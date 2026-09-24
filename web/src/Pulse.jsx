import { useState } from "react";
import { usd, age, fallbackAvatar } from "./api.js";

/*
  Three columns, and on this chain all three rest on a real field rather than
  on a proxy for one:

    New            newest by creation time
    Final stretch  sorted by how much the curve has actually taken
    Migrated       pump.fun's own `complete` flag, not a guess from age

  The bar under each row is curve progress. It only reaches full when the coin
  has migrated — a curve sitting past the threshold but still open is capped
  below full on purpose, because a full bar next to something that has not
  graduated is a lie the eye believes before the label corrects it.
*/

function Avatar({ row }) {
  const [src, setSrc] = useState(row.image_url || fallbackAvatar(row.mint));
  return (
    <img
      className="av" width="34" height="34" src={src} alt=""
      loading="lazy" referrerPolicy="no-referrer"
      onError={() => setSrc(fallbackAvatar(row.mint))}
    />
  );
}

function Row({ row, fresh, onOpen }) {
  const change = Number(row.change_h1) || 0;
  const pct = Math.round((Number(row.progress) || 0) * 100);
  return (
    <button className={`row${fresh ? " fresh" : ""}`} onClick={() => onOpen(row.mint)}>
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
          {row.indexed ? (
            <>
              <span>LP <b>{usd(row.liquidity_usd)}</b></span>
              <span>V1h <b>{usd(row.volume_h1)}</b></span>
              <span className={change >= 0 ? "up" : "down"}>
                {change >= 0 ? "+" : ""}{change.toFixed(1)}%
              </span>
            </>
          ) : (
            <span className="dim">no pool indexed</span>
          )}
          {row.can_inflate && <span className="down">mint open</span>}
          {row.can_freeze && <span className="down">freeze on</span>}
        </span>

        <span className="l3">
          <span className="bar"><i style={{ width: `${pct}%` }} /></span>
          <span className="dim tiny">{row.complete ? "migrated" : `${pct}% of curve`}</span>
        </span>
      </span>
    </button>
  );
}

function Column({ title, why, rows, freshest, onOpen }) {
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
            <Row key={row.mint} row={row} fresh={row.mint === freshest} onOpen={onOpen} />
          ))
        )}
      </div>
    </div>
  );
}

export default function Pulse({ columns, freshest, onOpen, filter }) {
  const pick = (list) => (list || []).filter(filter);
  return (
    <div className="pulse">
      <Column title="New" why="newest first" rows={pick(columns.new)} freshest={freshest} onOpen={onOpen} />
      <Column title="Final stretch" why="closest to migration" rows={pick(columns.stretch)} onOpen={onOpen} />
      <Column title="Migrated" why="curve finished" rows={pick(columns.migrated)} onOpen={onOpen} />
    </div>
  );
}
