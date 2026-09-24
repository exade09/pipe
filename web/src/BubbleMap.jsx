import { useMemo, useRef, useState } from "react";
import { short } from "./api.js";

/*
  The bubble map.

  Circles are wallets, area is share. Several token accounts belonging to one
  wallet collapse into a single circle, because a person holding through three
  accounts is one holder and drawing them apart would overstate how wide the
  book is.

  What this map deliberately does not draw: lines between wallets. On an EVM
  chain the transfer log gives funding relationships for nothing, so joining
  wallets that were funded from one address is honest and cheap. On Solana
  that needs signature history per wallet, which is a different order of cost,
  and drawing a relationship we have not verified would be worse than drawing
  none. The one relationship we do know — that a wallet belongs to the coin's
  creator — is marked in copper.
*/

const W = 760;
const H = 420;

function layout(holders) {
  const nodes = holders.slice(0, 40).map((h, i) => {
    const angle = (i * 2.39996) % (Math.PI * 2);
    const radius = 30 + (i % 9) * 19;
    return {
      h,
      x: W / 2 + Math.cos(angle) * radius,
      y: H / 2 + Math.sin(angle) * radius,
      r: Math.max(7, Math.sqrt(Math.max(h.share, 0.05)) * 13),
    };
  });

  for (let step = 0; step < 200; step++) {
    for (let a = 0; a < nodes.length; a++) {
      const A = nodes[a];
      A.x += (W / 2 - A.x) * 0.009;
      A.y += (H / 2 - A.y) * 0.009;
      for (let b = 0; b < nodes.length; b++) {
        if (a === b) continue;
        const B = nodes[b];
        const dx = A.x - B.x;
        const dy = A.y - B.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const need = A.r + B.r + 5;
        if (d < need) {
          const push = ((need - d) / d) * 0.5;
          A.x += dx * push; A.y += dy * push;
          B.x -= dx * push; B.y -= dy * push;
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
  const nodes = useMemo(() => layout(holders), [holders]);

  if (!holders.length) return <p className="note">No holder data for this coin.</p>;

  function move(event, node) {
    const box = wrapRef.current?.getBoundingClientRect();
    if (!box) return;
    setTip({ x: Math.min(box.width - 260, event.clientX - box.left + 12), y: event.clientY - box.top + 12, node });
  }

  return (
    <>
      <div className="bmwrap" ref={wrapRef}>
        <svg viewBox={`0 0 ${W} ${H}`} aria-label="Holder bubble map">
          {nodes.map((N, i) => {
            const colour = N.h.is_creator ? "#E8802A" : "#3A342E";
            return (
              <g key={i} className="bubble" onMouseMove={(e) => move(e, N.h)} onMouseLeave={() => setTip(null)}>
                <circle
                  cx={N.x.toFixed(1)} cy={N.y.toFixed(1)} r={N.r.toFixed(1)}
                  fill={colour} fillOpacity="0.22" stroke={colour} strokeWidth="1.2"
                />
                {N.r > 15 && (
                  <text x={N.x.toFixed(1)} y={(N.y + 3).toFixed(1)} textAnchor="middle" fontSize="9.5" fill={colour}>
                    {N.h.share.toFixed(1)}
                  </text>
                )}
              </g>
            );
          })}
        </svg>

        {tip && (
          <div className="tip" style={{ left: tip.x, top: tip.y }}>
            <b>{short(tip.node.owner || tip.node.account)}</b> · {tip.node.share.toFixed(2)}%
            {tip.node.is_creator && <span className="cu"> · creator</span>}
            {tip.node.accounts > 1 && <span> · {tip.node.accounts} accounts</span>}
          </div>
        )}

        <div className="bmlegend">
          {data.creator_share > 0 ? (
            <span><i style={{ background: "#E8802A" }} />creator · {data.creator_share.toFixed(1)}%</span>
          ) : (
            <span><i style={{ background: "#3A342E" }} />creator not among the largest</span>
          )}
          <span><i style={{ background: "#3A342E" }} />other wallets</span>
          {data.curve_share > 0 && <span>curve still holds {data.curve_share.toFixed(1)}%, excluded</span>}
          <span style={{ marginLeft: "auto" }}>{data.counted} wallets from the 20 largest accounts</span>
        </div>
      </div>

      <p className="note">
        Several token accounts owned by one wallet are drawn as one circle. No lines are drawn
        between wallets: on this chain a funding relationship needs signature history per wallet,
        and a line we have not verified would say more than we know. The creator's wallet is the
        one relationship the data does give, and it is marked.
      </p>
    </>
  );
}
