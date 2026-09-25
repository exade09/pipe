import { useMemo, useRef, useState } from "react";
import { short } from "./api.js";

const W = 840;
const H = 460;
const CX = W / 2;
const CY = H / 2;
const GOLDEN = 2.399963;

function seed(value = "") {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash);
}

function layout(holders) {
  const nodes = holders.slice(0, 40).map((holder, index) => {
    const offset = (seed(holder.owner || holder.account) % 628) / 100;
    const ring = index < 6 ? 0 : index < 18 ? 1 : 2;
    const targetRadius = 112 + ring * 82 + (seed(holder.account) % 17);
    const angle = index * GOLDEN + offset;
    const radius = Math.max(12, Math.min(58, 10 + Math.sqrt(Math.max(holder.share, 0.03)) * 8.2));
    return {
      holder,
      rank: index + 1,
      radius,
      targetX: CX + Math.cos(angle) * targetRadius,
      targetY: CY + Math.sin(angle) * targetRadius * 0.72,
      x: CX + Math.cos(angle) * targetRadius,
      y: CY + Math.sin(angle) * targetRadius * 0.72,
    };
  });

  for (let step = 0; step < 220; step += 1) {
    nodes.forEach((node, index) => {
      node.x += (node.targetX - node.x) * 0.025;
      node.y += (node.targetY - node.y) * 0.025;

      const centerDx = node.x - CX;
      const centerDy = node.y - CY;
      const centerDistance = Math.sqrt(centerDx ** 2 + centerDy ** 2) || 1;
      const centerLimit = node.radius + 64;
      if (centerDistance < centerLimit) {
        const push = (centerLimit - centerDistance) / centerDistance;
        node.x += centerDx * push;
        node.y += centerDy * push;
      }

      for (let otherIndex = index + 1; otherIndex < nodes.length; otherIndex += 1) {
        const other = nodes[otherIndex];
        const dx = node.x - other.x;
        const dy = node.y - other.y;
        const distance = Math.sqrt(dx ** 2 + dy ** 2) || 0.01;
        const needed = node.radius + other.radius + 7;
        if (distance < needed) {
          const push = ((needed - distance) / distance) * 0.52;
          node.x += dx * push;
          node.y += dy * push;
          other.x -= dx * push;
          other.y -= dy * push;
        }
      }

      node.x = Math.max(node.radius + 14, Math.min(W - node.radius - 14, node.x));
      node.y = Math.max(node.radius + 14, Math.min(H - node.radius - 14, node.y));
    });
  }
  return nodes;
}

function HolderDetail({ node, compact = false }) {
  if (!node) return null;
  const holder = node.holder || node;
  return (
    <div className={compact ? "bubble-detail compact" : "bubble-detail"}>
      <span className="lbl">{node.rank ? `Wallet #${node.rank}` : "Wallet"}</span>
      <b>{short(holder.owner || holder.account)}</b>
      <div><span>observed share</span><strong>{holder.share.toFixed(2)}%</strong></div>
      <div><span>token accounts</span><strong>{holder.accounts || 1}</strong></div>
      {holder.is_creator && <em>creator wallet</em>}
    </div>
  );
}

export default function BubbleMap({ data }) {
  const wrapRef = useRef(null);
  const [hovered, setHovered] = useState(null);
  const [selected, setSelected] = useState(null);
  const holders = data?.holders || [];
  const nodes = useMemo(() => layout(holders), [holders]);
  const active = hovered || selected;

  if (!holders.length) return <p className="note">No holder data is available for this token.</p>;

  return (
    <div className="bubble-panel">
      <div className="bubble-summary">
        <div><span className="lbl">Observed wallets</span><b>{data.counted}</b></div>
        <div><span className="lbl">Top 10 share</span><b>{data.top10_share.toFixed(1)}%</b></div>
        <div><span className="lbl">Creator share</span><b className={data.creator_share > 5 ? "hi" : ""}>{data.creator_share.toFixed(1)}%</b></div>
        <p>Area represents share of the observed holder set.</p>
      </div>

      <div className="bmwrap" ref={wrapRef}>
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Interactive holder concentration map">
          <defs>
            <pattern id="bubble-grid" width="32" height="32" patternUnits="userSpaceOnUse">
              <path d="M 32 0 L 0 0 0 32" fill="none" stroke="#17130f" strokeWidth="1" />
            </pattern>
            <radialGradient id="holder-fill" cx="36%" cy="30%">
              <stop offset="0" stopColor="#FFC46B" stopOpacity=".34" />
              <stop offset=".42" stopColor="#E8802A" stopOpacity=".15" />
              <stop offset="1" stopColor="#E8802A" stopOpacity=".04" />
            </radialGradient>
            <radialGradient id="creator-fill" cx="34%" cy="28%">
              <stop offset="0" stopColor="#FFD694" stopOpacity=".72" />
              <stop offset=".48" stopColor="#E8802A" stopOpacity=".32" />
              <stop offset="1" stopColor="#6D3211" stopOpacity=".13" />
            </radialGradient>
            <filter id="bubble-glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="5" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>

          <rect width={W} height={H} fill="url(#bubble-grid)" opacity=".72" />
          <circle className="orbit-ring" cx={CX} cy={CY} r="108" />
          <circle className="orbit-ring second" cx={CX} cy={CY} r="194" />
          <ellipse className="orbit-ring third" cx={CX} cy={CY} rx="304" ry="184" />

          <g className="map-core" transform={`translate(${CX} ${CY})`}>
            <circle r="48" />
            <circle className="core-scan" r="58" />
            <text y="-5">HOLDERS</text>
            <text className="core-value" y="15">{data.counted} wallets</text>
          </g>

          {nodes.map((node, index) => {
            const key = node.holder.owner || node.holder.account;
            const isActive = active && (active.holder.owner || active.holder.account) === key;
            const isDimmed = active && !isActive;
            const showShare = node.radius >= 23;
            return (
              <g
                key={key}
                className={`bubble-node${node.holder.is_creator ? " creator" : ""}${isActive ? " active" : ""}${isDimmed ? " dimmed" : ""}`}
                style={{ "--delay": `${Math.min(index * 22, 360)}ms` }}
                transform={`translate(${node.x.toFixed(1)} ${node.y.toFixed(1)})`}
                tabIndex="0"
                role="button"
                aria-label={`Wallet rank ${node.rank}, ${node.holder.share.toFixed(2)} percent`}
                onMouseEnter={() => setHovered(node)}
                onMouseLeave={() => setHovered(null)}
                onFocus={() => setHovered(node)}
                onBlur={() => setHovered(null)}
                onClick={() => setSelected(selected === node ? null : node)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setSelected(selected === node ? null : node);
                  }
                }}
              >
                <circle className="node-glow" r={(node.radius + 5).toFixed(1)} />
                <circle className="node-main" r={node.radius.toFixed(1)} />
                <text className="node-rank" y={showShare ? -3 : 3}>#{node.rank}</text>
                {showShare && <text className="node-share" y="13">{node.holder.share.toFixed(1)}%</text>}
                {node.holder.is_creator && <circle className="creator-mark" cx={node.radius * 0.68} cy={-node.radius * 0.68} r="4" />}
                <title>{short(key)} / {node.holder.share.toFixed(2)}%{node.holder.is_creator ? " / creator" : ""}</title>
              </g>
            );
          })}
        </svg>

        {active && <HolderDetail node={active} compact />}
        {selected && <button className="bubble-clear" onClick={() => setSelected(null)}>clear selection</button>}
      </div>

      <div className="bmlegend">
        <span><i className="legend-wallet" />wallet</span>
        <span><i className="legend-creator" />creator</span>
        {data.curve_share > 0 && <span>curve reserve excluded / {data.curve_share.toFixed(1)}%</span>}
        <span className="legend-note">hover or select a circle to inspect</span>
      </div>

      <p className="note bubble-note">
        The largest token accounts are resolved to their owning wallets, so several accounts held by
        one wallet become one circle. No wallet-to-wallet links are implied without verified transfer history.
      </p>
    </div>
  );
}
