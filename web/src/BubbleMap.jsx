import { useMemo, useRef, useState } from "react";
import { short, age } from "./api.js";

/*
  The bubble map.

  Circles are holders, area is proportional to share, and a line joins two
  wallets whose first tokens came from the same address. That is a real
  relationship and it is not proof of one person — the legend says so, and the
  read lists it under what could not be checked rather than under flags.

  Layout is a small relaxation pass rather than a physics library: forty nodes
  and two hundred iterations settle in a couple of milliseconds, and the result
  is deterministic for the same input, so the map does not rearrange itself
  every time the panel re-renders.
*/

const CLUSTER_COLOURS = ["#6C8FD6", "#B06CD6", "#D6B06C", "#6CD6B0", "#D66C8F"];
const W = 760;
const H = 420;

function layout(holders) {
  const nodes = holders.slice(0, 44).map((h, i) => {
    // deterministic start, so repeated renders land identically
    const angle = (i * 2.39996) % (Math.PI * 2);
    const radius = 30 + (i % 9) * 19;
    return {
      h,
      x: W / 2 + Math.cos(angle) * radius,
      y: H / 2 + Math.sin(angle) * radius,
      r: Math.max(6, Math.sqrt(Math.max(h.share, 0.02)) * 13),
    };
  });

  for (let step = 0; step < 200; step++) {
    for (let a = 0; a < nodes.length; a++) {
      const A = nodes[a];
      A.x += (W / 2 - A.x) * 0.009;
      A.y += (H / 2 - A.y) * 0.009;
      if (A.h.cluster >= 0) {
        for (const C of nodes) {
          if (C !== A && C.h.cluster === A.h.cluster) {
            A.x += (C.x - A.x) * 0.013;
            A.y += (C.y - A.y) * 0.013;
          }
        }
      }
      for (let b = 0; b < nodes.length; b++) {
        if (a === b) continue;
        const B = nodes[b];
        const dx = A.x - B.x;
        const dy = A.y - B.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const need = A.r + B.r + 5;
        if (d < need) {
          const push = ((need - d) / d) * 0.5;
          A.x += dx * push;
          A.y += dy * push;
          B.x -= dx * push;
          B.y -= dy * push;
        }
      }
      A.x = Math.max(A.r + 4, Math.min(W - A.r - 4, A.x));
      A.y = Math.max(A.r + 4, Math.min(H - A.r - 4, A.y));
    }
  }
  return nodes;
}

export default function BubbleMap({ data }) {
  const wrapRef = useRef(null);
  const [tip, setTip] = useState(null);

  const holders = data?.holders || [];
  const clusters = data?.clusters || [];
  const nodes = useMemo(() => layout(holders), [holders]);

  if (!holders.length) {
    return <p className="note">No holder data for this token yet.</p>;
  }

  const links = [];
  nodes.forEach((A, a) => {
    nodes.forEach((B, b) => {
      if (b <= a || A.h.cluster < 0 || A.h.cluster !== B.h.cluster) return;
      links.push(
        <line
          key={`${a}-${b}`}
          x1={A.x.toFixed(1)} y1={A.y.toFixed(1)}
          x2={B.x.toFixed(1)} y2={B.y.toFixed(1)}
          stroke={CLUSTER_COLOURS[A.h.cluster % 5]}
          strokeWidth="1" opacity="0.38"
        />
      );
    });
  });

  function move(event, node) {
    const box = wrapRef.current?.getBoundingClientRect();
    if (!box) return;
    setTip({
      x: Math.min(box.width - 250, event.clientX - box.left + 12),
      y: event.clientY - box.top + 12,
      node,
    });
  }

  return (
    <>
      <div className="bmwrap" ref={wrapRef}>
        <svg viewBox={`0 0 ${W} ${H}`} aria-label="Holder bubble map">
          {links}
          {nodes.map((N, i) => {
            const colour = N.h.is_deployer
              ? "#E8802A"
              : N.h.cluster >= 0
              ? CLUSTER_COLOURS[N.h.cluster % 5]
              : "#3A342E";
            return (
              <g
                key={i}
                className="bubble"
                onMouseMove={(e) => move(e, N.h)}
                onMouseLeave={() => setTip(null)}
              >
                <circle
                  cx={N.x.toFixed(1)} cy={N.y.toFixed(1)} r={N.r.toFixed(1)}
                  fill={colour} fillOpacity="0.22" stroke={colour} strokeWidth="1.2"
                />
                {N.r > 15 && (
                  <text
                    x={N.x.toFixed(1)} y={(N.y + 3).toFixed(1)}
                    textAnchor="middle" fontSize="9.5" fill={colour}
                  >
                    {N.h.share.toFixed(1)}
                  </text>
                )}
              </g>
            );
          })}
        </svg>

        {tip && (
          <div className="tip" style={{ left: tip.x, top: tip.y }}>
            <b>{short(tip.node.address)}</b> · {tip.node.share.toFixed(2)}%
            {tip.node.is_deployer && <span className="cu"> · deployer</span>}
            {tip.node.cluster >= 0 && <span> · cluster {tip.node.cluster + 1}</span>}
          </div>
        )}

        <div className="bmlegend">
          {data.deployer_share > 0 ? (
            <span><i style={{ background: "#E8802A" }} />deployer · {data.deployer_share.toFixed(1)}%</span>
          ) : (
            <span><i style={{ background: "#3A342E" }} />deployer holds nothing</span>
          )}
          {clusters.slice(0, 4).map((c) => (
            <span key={c.index}>
              <i style={{ background: CLUSTER_COLOURS[c.index % 5] }} />
              cluster {c.index + 1} · {c.wallets} wallets · {c.share}%
            </span>
          ))}
          <span><i style={{ background: "#3A342E" }} />unrelated</span>
          <span style={{ marginLeft: "auto" }}>
            read from {data.logs_read ?? "—"} transfer logs at block {data.taken_block}
          </span>
        </div>
      </div>

      <p className="note">
        A line joins two wallets whose first tokens came from the same address, ignoring
        purchases from the curve. That is evidence of a relationship, not proof of one:
        whether a cluster is one person, a market maker or a group chat is exactly what
        the read lists as unchecked rather than folding into a score.
      </p>
    </>
  );
}
