import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchCandles, priceText, usd } from "./api.js";

const FRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"];
const ZOOM_LEVELS = [36, 54, 72, 96, 132, 180];
const H = 430;
const VOL_H = 82;
const PAD = { top: 22, right: 98, bottom: 30, left: 10 };

function ticks(low, high, count = 5) {
  if (!(high > low)) return [low];
  const step = (high - low) / count;
  return Array.from({ length: count + 1 }, (_, i) => low + step * i);
}

function timeLabel(seconds, frame, detailed = false) {
  const d = new Date(seconds * 1000);
  if (detailed) {
    return d.toLocaleString(undefined, {
      month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  }
  if (frame === "1d" || frame === "4h") return `${d.getDate()}/${d.getMonth() + 1}`;
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export default function Chart({ mint, symbol }) {
  const [frame, setFrame] = useState("1m");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const [hover, setHover] = useState(null);
  const [visibleBars, setVisibleBars] = useState(96);
  const [W, setW] = useState(900);
  const svgRef = useRef(null);
  const boxRef = useRef(null);

  useEffect(() => {
    const measure = () => {
      const width = boxRef.current?.clientWidth;
      if (width) setW(Math.max(320, Math.round(width)));
    };
    measure();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null;
    if (observer && boxRef.current) observer.observe(boxRef.current);
    window.addEventListener("resize", measure);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, []);

  const load = useCallback(async (signal) => {
    setBusy(true);
    try {
      const next = await fetchCandles(mint, frame, signal);
      setData(next);
      setError("");
    } catch (e) {
      if (e.name !== "AbortError") setError(e.message);
    } finally {
      if (!signal?.aborted) setBusy(false);
    }
  }, [mint, frame]);

  useEffect(() => {
    const ctrl = new AbortController();
    setHover(null);
    load(ctrl.signal);
    const timer = setInterval(() => load(), 20000);
    return () => {
      ctrl.abort();
      clearInterval(timer);
    };
  }, [load]);

  const view = useMemo(() => {
    const bars = data?.bars || [];
    if (!bars.length) return null;
    const plotW = W - PAD.left - PAD.right;
    const capacity = Math.max(18, Math.floor(plotW / 8));
    const shown = bars.slice(-Math.min(visibleBars, capacity));
    const rawLow = Math.min(...shown.map((bar) => bar.l));
    const rawHigh = Math.max(...shown.map((bar) => bar.h));
    const spread = rawHigh - rawLow;
    const pad = spread * 0.1 || rawHigh * 0.035 || 1e-9;
    const top = rawHigh + pad;
    const bottom = Math.max(0, rawLow - pad);
    const priceBottom = H - PAD.bottom - VOL_H;
    const plotH = priceBottom - PAD.top;
    const step = plotW / shown.length;
    const volMax = Math.max(...shown.map((bar) => bar.v), 1e-9);
    return {
      shown, top, bottom, step, volMax, priceBottom,
      x: (i) => PAD.left + i * step + step / 2,
      y: (price) => PAD.top + ((top - price) / (top - bottom || 1)) * plotH,
    };
  }, [data, W, visibleBars]);

  const zoom = (direction) => {
    const index = ZOOM_LEVELS.reduce((best, level, i) => (
      Math.abs(level - visibleBars) < Math.abs(ZOOM_LEVELS[best] - visibleBars) ? i : best
    ), 0);
    const next = Math.max(0, Math.min(ZOOM_LEVELS.length - 1, index + direction));
    setVisibleBars(ZOOM_LEVELS[next]);
    setHover(null);
  };

  const onMove = (event) => {
    if (!view || !svgRef.current) return;
    const box = svgRef.current.getBoundingClientRect();
    const px = ((event.clientX - box.left) / box.width) * W;
    const index = Math.round((px - PAD.left - view.step / 2) / view.step);
    setHover(Math.max(0, Math.min(view.shown.length - 1, index)));
  };

  const last = view ? view.shown[view.shown.length - 1] : null;
  const first = view ? view.shown[0] : null;
  const move = last && first ? ((last.c - first.o) / (first.o || 1)) * 100 : 0;
  const active = hover != null && view ? view.shown[hover] : last;
  const every = view ? Math.max(1, Math.ceil(view.shown.length / 7)) : 1;
  const waiting = /waiting|not indexed|no candles|too few|has not published/i.test(error);
  const source = data?.source === "on-chain curve" ? "on-chain curve trades" : "DEX OHLCV";
  const venue = data?.pool?.startsWith("curve:") ? "live curve" : data?.dex || "market";

  return (
    <div className="chart" ref={boxRef}>
      <div className="chart-toolbar">
        <div className="frames" aria-label="Chart timeframe">
          {FRAMES.map((value) => (
            <button key={value} className="fr" aria-pressed={value === frame} onClick={() => setFrame(value)}>
              {value}
            </button>
          ))}
        </div>
        <span className="grow" />
        {view && (
          <span className={`chart-change ${move >= 0 ? "up" : "down"}`}>
            {move >= 0 ? "+" : ""}{move.toFixed(2)}%
          </span>
        )}
        <div className="chart-zoom" aria-label="Chart zoom">
          <button title="Zoom in" onClick={() => zoom(-1)} disabled={visibleBars === ZOOM_LEVELS[0]}>+</button>
          <button title="Zoom out" onClick={() => zoom(1)} disabled={visibleBars === ZOOM_LEVELS.at(-1)}>-</button>
          <button title="Reset zoom" onClick={() => setVisibleBars(96)}>reset</button>
        </div>
        {busy && <span className="chart-live"><i />sync</span>}
        {data?.stale && <span className="chip warn"><i />stale</span>}
      </div>

      {active && (
        <div className="chart-readout">
          <b>{symbol}/USD</b>
          <span>{timeLabel(active.t, frame, true)}</span>
          <span>O <strong>{priceText(active.o)}</strong></span>
          <span>H <strong>{priceText(active.h)}</strong></span>
          <span>L <strong>{priceText(active.l)}</strong></span>
          <span>C <strong className={active.c >= active.o ? "up" : "down"}>{priceText(active.c)}</strong></span>
          <span>Vol <strong>{usd(active.v)}</strong></span>
        </div>
      )}

      {error && <p className={`chart-msg ${waiting ? "waiting" : "err"}`}>{error}</p>}
      {!data && !error && <p className="chart-msg loading">reading confirmed trades</p>}

      {view && !error && (
        <div className="chart-stage">
          <svg
            ref={svgRef}
            viewBox={`0 0 ${W} ${H}`}
            width={W}
            height={H}
            className="chart-svg"
            onMouseMove={onMove}
            onMouseLeave={() => setHover(null)}
            onWheel={(event) => {
              event.preventDefault();
              zoom(event.deltaY < 0 ? -1 : 1);
            }}
          >
            <rect className="plot-bg" x="0" y="0" width={W} height={H} />

            {ticks(view.bottom, view.top).map((price, i) => (
              <g key={`g${i}`}>
                <line className="grid" x1={PAD.left} x2={W - PAD.right} y1={view.y(price)} y2={view.y(price)} />
                <text className="axis price-axis" x={W - PAD.right + 9} y={view.y(price) + 3.5}>
                  {priceText(price)}
                </text>
              </g>
            ))}

            {view.shown.map((bar, i) => i % every === 0 ? (
              <g key={`t${bar.t}`}>
                <line className="grid vertical" x1={view.x(i)} x2={view.x(i)} y1={PAD.top} y2={H - PAD.bottom} />
                <text className="axis mid" x={view.x(i)} y={H - 8}>{timeLabel(bar.t, frame)}</text>
              </g>
            ) : null)}

            <line className="volume-rule" x1={PAD.left} x2={W - PAD.right} y1={view.priceBottom + 12} y2={view.priceBottom + 12} />
            <text className="axis volume-label" x={PAD.left + 4} y={view.priceBottom + 26}>VOLUME</text>

            {view.shown.map((bar, i) => {
              const width = Math.max(3, Math.min(12, view.step * 0.58));
              const volumeHeight = (bar.v / view.volMax) * (VOL_H - 25);
              const bodyTop = view.y(Math.max(bar.o, bar.c));
              const bodyHeight = Math.max(2, Math.abs(view.y(bar.o) - view.y(bar.c)));
              return (
                <g key={bar.t} className={`cndl ${bar.c >= bar.o ? "up" : "down"}`}>
                  <line className="wick" x1={view.x(i)} x2={view.x(i)} y1={view.y(bar.h)} y2={view.y(bar.l)} />
                  <rect className="body" x={view.x(i) - width / 2} y={bodyTop} width={width} height={bodyHeight} rx="1" />
                  <rect className="vol" x={view.x(i) - width / 2} y={H - PAD.bottom - volumeHeight} width={width} height={Math.max(1, volumeHeight)} rx="1" />
                </g>
              );
            })}

            {last && (
              <g>
                <line className="lastline" x1={PAD.left} x2={W - PAD.right} y1={view.y(last.c)} y2={view.y(last.c)} />
                <rect className="lastbox" x={W - PAD.right + 3} y={view.y(last.c) - 10} width={PAD.right - 6} height={20} />
                <text className="lasttext" x={W - PAD.right + 10} y={view.y(last.c) + 4}>{priceText(last.c)}</text>
              </g>
            )}

            {hover != null && active && (
              <g className="crosshair">
                <line className="cross" x1={view.x(hover)} x2={view.x(hover)} y1={PAD.top} y2={H - PAD.bottom} />
                <line className="cross" x1={PAD.left} x2={W - PAD.right} y1={view.y(active.c)} y2={view.y(active.c)} />
                <circle className="cross-dot" cx={view.x(hover)} cy={view.y(active.c)} r="3" />
              </g>
            )}
          </svg>
          {view.shown.length === 1 && (
            <span className="chart-collecting">first confirmed bar / collecting live history</span>
          )}
        </div>
      )}

      {data && (
        <div className="chart-foot">
          <span><i className="source-dot" />{venue}</span>
          <span>{view?.shown.length || 0} / {data.bars.length} bars visible</span>
          <span className="grow" />
          <span>{source} / {frame} / refresh 20s</span>
        </div>
      )}
    </div>
  );
}
