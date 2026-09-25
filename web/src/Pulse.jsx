import { useState } from "react";
import { usd, age } from "./api.js";
import Avatar from "./Avatar.jsx";

/*
  Three columns, and on this chain all three rest on a real field rather than
  on a proxy for one:

    New            newest by creation time
    Final stretch  sorted by how much the curve has actually taken
    Migrated       pump.fun's own `complete` flag, not a guess from age

  A row is a card with a fixed rhythm: avatar, three lines, and a right edge
  that carries the age and the action. Every line is one line — nothing wraps,
  because a column of cards that each choose their own height reads as a list
  of paragraphs rather than as a feed, and the eye loses the left edge.

  So the facts are short. `mint ✓` rather than MINT REVOKED: the reader is
  scanning for the absence of a red pill, not reading sentences. Anything that
  will not fit is clipped at the card edge instead of pushing the card taller.

  Curve progress is the hairline along the bottom of the card. It belongs to
  the card, not to a row inside it, and it only reaches the full width for a
  coin that has migrated — a curve past the threshold but still open is capped
  short on purpose, because a full bar next to something that has not
  graduated is a lie the eye believes before the label corrects it.
*/

function Face({ row }) {
  return (
    <span className="avwrap">
      <Avatar url={row.image_url} mint={row.mint} size={40} />
      <i className={`dot ${row.risk || "watch"}`} />
    </span>
  );
}

function Pills({ row }) {
  const pills = [];

  if (!row.mint_readable) {
    pills.push(["mint ?", "warn"]);
  } else {
    pills.push(row.can_inflate ? ["mint live", "bad"] : ["mint ✓", "good"]);
    pills.push(row.can_freeze ? ["freeze on", "bad"] : ["freeze ✓", "good"]);
  }

  if (row.indexed) {
    const buys = Number(row.buys_h1) || 0;
    const sells = Number(row.sells_h1) || 0;
    if (buys + sells > 0) pills.push([`${buys}b/${sells}s`, buys >= sells ? "good" : ""]);
  } else {
    pills.push(["no pool", ""]);
  }

  if (row.reply_count > 0) pills.push([`${row.reply_count}r`, ""]);

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
      title={`${row.symbol || "?"} — ${row.name || ""}`}
    >
      <Face row={row} />

      <span className="mid">
        <span className="l1">
          <span className="s">{row.symbol || "?"}</span>
          <span className="nm">{row.name || ""}</span>
        </span>

        <span className="l2">
          <span className="kv1">MC <b>{usd(row.fdv)}</b></span>
          {row.indexed ? (
            <>
              <span className="kv1">LP <b>{usd(row.liquidity_usd)}</b></span>
              <span className="kv1">V <b>{usd(row.volume_h1)}</b></span>
              <span className={change >= 0 ? "up" : "down"}>
                {change >= 0 ? "+" : ""}{change.toFixed(1)}%
              </span>
            </>
          ) : (
            <span className="kv1 dim">{row.complete ? "pool not indexed" : `${pct}% of curve`}</span>
          )}
        </span>

        <Pills row={row} />
      </span>

      <span className="right">
        <span className="age">{age(row.age_minutes)}</span>
        <span className="buy" aria-hidden="true">buy</span>
      </span>

      <span className={`edge${row.complete ? " done" : ""}`}><i style={{ width: `${pct}%` }} /></span>
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
