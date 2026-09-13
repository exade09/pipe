import { useState } from "react";
import { usd, age, fallbackAvatar } from "./api.js";

/*
  Three columns, and each one is a genuinely different question rather than
  three slices of the same sort:

    New       what has just been deployed, newest block first
    Gaining   what has been indexed and is actually trading, by hour volume
    Deepest   what has real liquidity behind the quote

  Curve progress toward migration is not read yet — the curve ABI has not been
  verified against the deployed bytecode, and a column labelled "final stretch"
  that was really "sorted by age" would be a lie in the shape of a feature.
*/

function Avatar({ row }) {
  const [src, setSrc] = useState(row.image_url || fallbackAvatar(row.address));
  return (
    <img
      className="av" width="34" height="34" src={src} alt=""
      loading="lazy"
      onError={() => setSrc(fallbackAvatar(row.address))}
    />
  );
}

function Row({ row, fresh, onOpen }) {
  const change = Number(row.change_h1) || 0;
  return (
    <button className={`row${fresh ? " fresh" : ""}`} onClick={() => onOpen(row.address)}>
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
          {row.indexed ? (
            <>
              <span>MC <b>{usd(row.fdv)}</b></span>
              <span>LP <b>{usd(row.liquidity_usd)}</b></span>
              <span>V1h <b>{usd(row.volume_h1)}</b></span>
              <span className={change >= 0 ? "up" : "down"}>
                {change >= 0 ? "+" : ""}{change.toFixed(1)}%
              </span>
            </>
          ) : (
            <>
              <span className="dim">not indexed yet</span>
              <span className="dim">· {row.native_pair ? "ETH pair" : "equity pair"}</span>
            </>
          )}
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
            <Row key={row.address} row={row} fresh={row.address === freshest} onOpen={onOpen} />
          ))
        )}
      </div>
    </div>
  );
}

export default function Pulse({ rows, freshest, onOpen }) {
  const fresh = [...rows].sort((a, b) => b.launch_block - a.launch_block).slice(0, 60);
  const gaining = rows
    .filter((r) => r.indexed && Number(r.volume_h1) > 0)
    .sort((a, b) => b.volume_h1 - a.volume_h1)
    .slice(0, 60);
  const deepest = rows
    .filter((r) => Number(r.liquidity_usd) > 0)
    .sort((a, b) => b.liquidity_usd - a.liquidity_usd)
    .slice(0, 60);

  return (
    <div className="pulse">
      <Column title="New" why="newest block first" rows={fresh} freshest={freshest} onOpen={onOpen} />
      <Column title="Gaining" why="by volume, last hour" rows={gaining} onOpen={onOpen} />
      <Column title="Deepest" why="by liquidity" rows={deepest} onOpen={onOpen} />
    </div>
  );
}
