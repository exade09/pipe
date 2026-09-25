import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchCandles, priceText, usd } from "./api.js";

/*
  The chart.

  Three columns of numbers can say what a coin is worth and cannot say what
  shape it is in — whether it is climbing, bleeding, or has been flat since
  the day it migrated. That is the one question a chart answers better than
  any table, so this is the only drawing in the terminal that earns its space.

  It is plain SVG on purpose. A charting library would bring its own type
  scale, its own greys and its own idea of a tooltip, and the page would start
  to look like two products stitched together. Candles are rectangles and
  lines; what drawing them by hand buys is a chart that reads as part of the
  same terminal.

  Prices here span six orders of magnitude between one coin and the next, so
  the vertical scale is fitted to the window on screen rather than anchored to
  zero. A meme that moved 4% should not get a flat line because its price
  happens to have four leading zeros.
*/

const FRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"];

/*
  The drawing is laid out in real pixels rather than in a fixed viewBox scaled
  to fit. A viewBox that stretches would stretch the axis labels with it, and
  the rail this chart sits beside is narrow — so the width is measured and the
  candles are spaced to it, which keeps type at its true size at every width.
*/
const H = 340;
const VOL_H = 64;
const PAD = { top: 14, right: 78, bottom: 22, left: 8 };

function ticks(low, high, count = 5) {
  if (!(high > low)) return [low];
  const step = (high - low) / count;
  return Array.from({ length: count + 1 }, (_, i) => low + step * i);
}

function timeLabel(seconds, frame) {
  const d = new Date(seconds * 1000);
  if (frame === "1d" || frame === "4h") return `${d.getDate()}/${d.getMonth() + 1}`;
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export default function Chart({ mint, symbol }) {
  const [frame, setFrame] = useState("5m");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [hover, setHover] = useState(null);
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

  const load = useCallback(
    async (signal) => {
      try {
        setData(await fetchCandles(mint, frame, signal));
        setError("");
      } catch (e) {
        if (e.name !== "AbortError") setError(e.message);
      }
    },
    [mint, frame],
  );

  useEffect(() => {
    const ctrl = new AbortController();
    setData(null);
    setError("");
    setHover(null);
    load(ctrl.signal);
    // GeckoTerminal's free tier is measured at about two calls before it
    // blocks, so the refresh is slow on purpose. Stale candles that say they
    // are stale beat a chart that keeps asking for a refusal.
    const timer = setInterval(() => load(), 30000);
    return () => {
      ctrl.abort();
      clearInterval(timer);
    };
  }, [load]);

  const view = useMemo(() => {
    const bars = data?.bars || [];
    if (bars.length < 2) return null;
    // One bar narrower than about three pixels is a line, not a candle, so the
    // window shrinks with the panel rather than cramming 180 bars into it.
    const room = Math.max(24, Math.floor((W - PAD.left - PAD.right) / 4));
    const shown = bars.slice(-Math.min(180, room));
    const low = Math.min(...shown.map((b) => b.l));
    const high = Math.max(...shown.map((b) => b.h));
    const pad = (high - low) * 0.08 || high * 0.04 || 1;
    const top = high + pad;
    const bottom = Math.max(0, low - pad);
    const plotH = H - PAD.top - PAD.bottom - VOL_H;
    const step = (W - PAD.left - PAD.right) / shown.length;
    const volMax = Math.max(...shown.map((b) => b.v), 1);
    return {
      shown,
      top,
      bottom,
      step,
      volMax,
      x: (i) => PAD.left + i * step + step / 2,
      y: (price) => PAD.top + ((top - price) / (top - bottom || 1)) * plotH,
    };
  }, [data, W]);

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
  const every = view ? Math.ceil(view.shown.length / 7) : 1;

  return (
    <div className="chart" ref={boxRef}>
      <div className="chart-head">
        <span className="frames">
          {FRAMES.map((f) => (
            <button key={f} className="fr" aria-pressed={f === frame} onClick={() => setFrame(f)}>
              {f}
            </button>
          ))}
        </span>
        {active && (
          <span className="ohlc">
            <span>O <b>{priceText(active.o)}</b></span>
            <span>H <b>{priceText(active.h)}</b></span>
            <span>L <b>{priceText(active.l)}</b></span>
            <span>C <b className={active.c >= active.o ? "up" : "down"}>{priceText(active.c)}</b></span>
            <span>V <b>{usd(active.v)}</b></span>
          </span>
        )}
        <span className="grow" />
        {view && (
          <span className={move >= 0 ? "up" : "down"}>
            {move >= 0 ? "+" : ""}
            {move.toFixed(1)}% over {view.shown.length} bars
          </span>
        )}
        {data?.stale && (
          <span className="chip warn" title="GeckoTerminal is rate limiting us; these are the last candles it served">
            <i />stale
          </span>
        )}
      </div>

      {error && <p className="chart-msg err">{error}</p>}
      {!data && !error && <p className="chart-msg loading">reading candles</p>}
      {data && !view && !error && (
        <p className="chart-msg">
          {symbol} has traded too few times for a chart — {data.bars.length} bar
          {data.bars.length === 1 ? "" : "s"} on this timeframe.
        </p>
      )}

      {view && (
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          width={W}
          height={H}
          className="chart-svg"
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
        >
          {ticks(view.bottom, view.top).map((price, i) => (
            <g key={`g${i}`}>
              <line className="grid" x1={PAD.left} x2={W - PAD.right} y1={view.y(price)} y2={view.y(price)} />
              <text className="axis" x={W - PAD.right + 7} y={view.y(price) + 3.5}>
                {priceText(price)}
              </text>
            </g>
          ))}

          {view.shown.map((bar, i) =>
            i % every === 0 ? (
              <text key={`t${bar.t}`} className="axis mid" x={view.x(i)} y={H - 6}>
                {timeLabel(bar.t, frame)}
              </text>
            ) : null,
          )}

          {view.shown.map((bar, i) => {
            const w = Math.max(1, view.step * 0.62);
            const volH = (bar.v / view.volMax) * (VOL_H - 10);
            return (
              <g key={bar.t} className={bar.c >= bar.o ? "cndl up" : "cndl down"}>
                <line className="wick" x1={view.x(i)} x2={view.x(i)} y1={view.y(bar.h)} y2={view.y(bar.l)} />
                <rect
                  className="body"
                  x={view.x(i) - w / 2}
                  y={view.y(Math.max(bar.o, bar.c))}
                  width={w}
                  height={Math.max(1, Math.abs(view.y(bar.o) - view.y(bar.c)))}
                />
                <rect
                  className="vol"
                  x={view.x(i) - w / 2}
                  y={H - PAD.bottom - volH}
                  width={w}
                  height={Math.max(0.6, volH)}
                />
              </g>
            );
          })}

          {last && (
            <g>
              <line className="lastline" x1={PAD.left} x2={W - PAD.right} y1={view.y(last.c)} y2={view.y(last.c)} />
              <rect className="lastbox" x={W - PAD.right + 2} y={view.y(last.c) - 8} width={PAD.right - 4} height={16} />
              <text className="lasttext" x={W - PAD.right + 7} y={view.y(last.c) + 3.5}>
                {priceText(last.c)}
              </text>
            </g>
          )}

          {hover != null && (
            <line className="cross" x1={view.x(hover)} x2={view.x(hover)} y1={PAD.top} y2={H - PAD.bottom} />
          )}
        </svg>
      )}

      {data && (
        <div className="chart-foot">
          <span>
            {data.dex || "pool"} · {data.pool.slice(0, 4)}…{data.pool.slice(-4)}
          </span>
          <span className="grow" />
          <span>ohlcv from geckoterminal · {frame} bars · refreshed every 30s</span>
        </div>
      )}
    </div>
  );
}
