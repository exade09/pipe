from __future__ import annotations

"""
Candles.

A terminal without a chart is a table, and the one thing the three columns
cannot show is shape: whether a coin is climbing, bleeding, or has been flat
since it migrated. So the token page needs OHLCV, and on Solana there is
exactly one source that serves it without a key — GeckoTerminal.

Two things about that API, both learned by trying:

  · it wants the browser Origin. Without `Origin: https://www.geckoterminal.com`
    the OHLCV path answers 403 while the pool path answers 200, which reads
    like a broken endpoint and is really a bot check.
  · the free tier is thin. Two calls land, the third is refused, and the
    refusal is a Cloudflare page rather than a 429. Measured, not read.

Both of those shape the code below. Every answer is cached, and the last good
answer is kept past its TTL: when the ceiling is hit the chart keeps the
candles it has and says they are a minute old, which is the honest thing and
also the useful one. A refusal opens a short circuit breaker so the next
viewer does not spend their request finding the same wall.

There are two caches, and the second one is the one that matters in
production. Process memory is fast and per-instance; on a serverless host that
means it is empty for most requests, and a hundred readers would spend a
hundred calls against a budget of two. So when a database is configured the
bars go there as well, and one row decides which single instance is allowed
upstream at all — everyone else reads what that instance wrote. Without a
database nothing breaks; the terminal simply falls back to memory and says
"stale" more often.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pipe import db
from pipe.config import GECKOTERMINAL_BASE, GECKOTERMINAL_NETWORK, user_agent


class CandlesUnavailable(RuntimeError):
    """No candles, and none cached — the caller should say so, not draw zero."""


# label -> (geckoterminal path, aggregate, seconds per bar)
TIMEFRAMES: dict[str, tuple[str, int, int]] = {
    "1m": ("minute", 1, 60),
    "5m": ("minute", 5, 300),
    "15m": ("minute", 15, 900),
    "1h": ("hour", 1, 3600),
    "4h": ("hour", 4, 14400),
    "1d": ("day", 1, 86400),
}

# Which timeframe is actually fetched for each one the reader can ask for.
#
# Six timeframes against a budget of about two calls a minute would mean every
# click on the switcher hits a wall. But candles compose: five one-minute bars
# are a five-minute bar, open from the first, close from the last, high and low
# from all of them. So three fetches cover all six, and switching between the
# derived ones costs nothing at all.
SOURCE = {"1m": "1m", "5m": "1m", "15m": "1m", "1h": "1h", "4h": "1h", "1d": "1d"}

POOL_TTL = 600.0
BAR_TTL = 20.0
BREAKER_SECONDS = 45.0

_pools: dict[str, tuple[float, list[dict]]] = {}
_bars: dict[str, tuple[float, dict]] = {}
_blocked_until = 0.0


@dataclass
class Series:
    mint: str
    pool: str
    dex: str
    timeframe: str
    bars: list[dict] = field(default_factory=list)
    fetched_at: float = 0.0
    stale: bool = False


def _get(path: str, params: dict | None = None, timeout: int = 20) -> Any:
    """
    One call, with the headers the endpoint actually requires. A 403 is the
    rate ceiling rather than an error in the request, so it opens the breaker
    instead of being retried into the same wall.
    """
    global _blocked_until
    url = f"{GECKOTERMINAL_BASE}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    request = Request(
        url,
        headers={
            "Accept": "application/json;version=20230302",
            "User-Agent": user_agent(),
            "Origin": "https://www.geckoterminal.com",
            "Referer": "https://www.geckoterminal.com/",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in (403, 429):
            _blocked_until = time.monotonic() + BREAKER_SECONDS
        return None
    except (URLError, TimeoutError, json.JSONDecodeError):
        return None


def throttled() -> bool:
    """True while the free tier is refusing us, so callers can say which it is."""
    return time.monotonic() < _blocked_until


def pools_for(mint: str) -> list[dict]:
    """
    Every pool that has indexed the coin, deepest first. Deepest is the one
    worth charting: the others are dust pairs whose candles are noise.
    """
    hit = _pools.get(mint)
    now = time.time()
    if hit and now - hit[0] < POOL_TTL:
        return hit[1]
    if throttled() and hit:
        return hit[1]

    raw = _get(f"/networks/{GECKOTERMINAL_NETWORK}/tokens/{mint}/pools", {"page": 1})
    out: list[dict] = []
    for item in ((raw or {}).get("data") or []):
        attrs = item.get("attributes") or {}
        address = attrs.get("address")
        if not address:
            continue
        try:
            liquidity = float(attrs.get("reserve_in_usd") or 0)
        except (TypeError, ValueError):
            liquidity = 0.0
        out.append(
            {
                "address": address,
                "name": attrs.get("name") or "",
                "dex": ((item.get("relationships") or {}).get("dex") or {}).get("data", {}).get("id", ""),
                "liquidity_usd": liquidity,
            }
        )
    out.sort(key=lambda p: p["liquidity_usd"], reverse=True)
    if out:
        _pools[mint] = (now, out)
        return out
    return hit[1] if hit else []


def _parse(raw: Any) -> list[dict]:
    """
    GeckoTerminal returns [ts, o, h, l, c, v] newest first. Charts read left
    to right, so the reversal happens once, here.
    """
    rows = (((raw or {}).get("data") or {}).get("attributes") or {}).get("ohlcv_list") or []
    bars: list[dict] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 6:
            continue
        try:
            bars.append(
                {
                    "t": int(row[0]),
                    "o": float(row[1]),
                    "h": float(row[2]),
                    "l": float(row[3]),
                    "c": float(row[4]),
                    "v": float(row[5]),
                }
            )
        except (TypeError, ValueError):
            continue
    bars.sort(key=lambda b: b["t"])
    return bars


def _roll(bars: list[dict], seconds: int) -> list[dict]:
    """
    Finer bars into coarser ones. Open comes from the first bar in the bucket,
    close from the last, high and low from all of them, volume summed — which
    is what a candle of that length would have been had it been fetched.
    """
    out: list[dict] = []
    for bar in bars:
        stamp = bar["t"] - (bar["t"] % seconds)
        if out and out[-1]["t"] == stamp:
            top = out[-1]
            top["h"] = max(top["h"], bar["h"])
            top["l"] = min(top["l"], bar["l"])
            top["c"] = bar["c"]
            top["v"] += bar["v"]
        else:
            out.append({"t": stamp, "o": bar["o"], "h": bar["h"], "l": bar["l"], "c": bar["c"], "v": bar["v"]})
    return out


def fetch_source(pool: str, source: str, limit: int = 1000) -> list[dict]:
    """One timeframe straight from GeckoTerminal, no caching. The cron's door."""
    if source not in TIMEFRAMES:
        return []
    return _upstream(pool, source, limit)


def _upstream(pool: str, source: str, limit: int) -> list[dict]:
    unit, aggregate, _ = TIMEFRAMES[source]
    return _parse(
        _get(
            f"/networks/{GECKOTERMINAL_NETWORK}/pools/{pool}/ohlcv/{unit}",
            {"aggregate": aggregate, "limit": min(max(limit, 10), 1000), "currency": "usd"},
        )
    )


def _merge(old: list[dict], new: list[dict]) -> list[dict]:
    """
    Stored bars plus fetched ones, newest version of each timestamp winning.
    This is where history accumulates: GeckoTerminal serves a window, and
    keeping the old window means the chart reaches back further than any single
    call ever could.
    """
    if not old:
        return new
    by_time = {bar["t"]: bar for bar in old}
    by_time.update({bar["t"]: bar for bar in new})
    return sorted(by_time.values(), key=lambda b: b["t"])


def _fetch(pool: str, source: str, limit: int) -> tuple[list[dict], float, bool]:
    """
    One source timeframe for one pool. Returns the bars, when they were taken,
    and whether they are being served past their TTL — which happens either
    because the free tier refused a refresh or because another instance is
    holding the fetch and this one is reading what it stored.
    """
    key = f"{pool}:{source}"
    hit = _bars.get(key)
    now = time.time()
    if hit and now - hit[0] < BAR_TTL:
        return hit[1]["bars"], hit[0], False

    stored: list[dict] = []
    age: float | None = None
    if db.configured():
        try:
            stored = db.read_candles(pool, source, 1000)
            age = db.candle_age(pool, source)
        except Exception:
            # A database that is unreachable is a slower terminal, not a
            # broken one: everything below still works off memory.
            stored, age = [], None

        if stored and age is not None and age < BAR_TTL:
            _bars[key] = (now - age, {"bars": stored})
            return stored, now - age, False

        # Exactly one instance goes upstream per TTL. The rest read what it
        # wrote, which is the whole reason the shared table exists.
        if not throttled():
            try:
                mine = db.claim_candle_fetch(pool, source, BAR_TTL)
            except Exception:
                mine = True
            if mine:
                fresh = _upstream(pool, source, limit)
                if fresh:
                    merged = _merge(stored, fresh)
                    try:
                        db.save_candles(pool, source, fresh)
                    except Exception:
                        pass
                    _bars[key] = (now, {"bars": merged})
                    return merged, now, False

        if stored:
            taken = now - (age or BAR_TTL)
            _bars[key] = (taken, {"bars": stored})
            return stored, taken, True

    if throttled() and hit:
        return hit[1]["bars"], hit[0], True

    fresh = _upstream(pool, source, limit)
    if fresh:
        merged = _merge(hit[1]["bars"] if hit else [], fresh)
        _bars[key] = (now, {"bars": merged})
        return merged, now, False
    if hit:
        return hit[1]["bars"], hit[0], True
    return [], 0.0, False


# How many buckets a timeframe shows. One number for every frame, so 1m is the
# last three hours and 1d is the last six months, and no frame is ever asked to
# draw a year of silence.
WINDOW_BARS = 180


def densify(bars: list[dict], seconds: int, window: int = WINDOW_BARS) -> tuple[list[dict], int]:
    """
    A continuous run of buckets ending at the newest bar.

    OHLCV sources only emit a bar where something traded. Drawing those side by
    side puts a bar from March next to a bar from today and labels the gap as
    one minute, which is how a quiet coin ends up looking like a chart of five
    enormous candles. So the run is clamped to the last `window` buckets and
    every empty bucket inside it is filled with a flat bar at the previous
    close, carrying no volume and marked `f` so the chart can draw it as the
    nothing that it is.

    Returns the bars and how many of them were real trades.
    """
    if not bars:
        return [], 0
    ordered = sorted(bars, key=lambda b: b["t"])
    end = ordered[-1]["t"] - (ordered[-1]["t"] % seconds)
    start = end - seconds * (window - 1)
    real = {bar["t"] - (bar["t"] % seconds): bar for bar in ordered if bar["t"] >= start}
    if not real:
        return [], 0

    out: list[dict] = []
    close = real[min(real)]["o"]
    for stamp in range(min(real), end + seconds, seconds):
        hit = real.get(stamp)
        if hit:
            out.append(dict(hit, t=stamp))
            close = hit["c"]
        else:
            out.append({"t": stamp, "o": close, "h": close, "l": close, "c": close, "v": 0.0, "f": True})
    return out, len(real)


def series(mint: str, timeframe: str = "5m", limit: int = 300, pool: str = "") -> Series:
    if timeframe not in TIMEFRAMES:
        timeframe = "5m"

    dex = ""
    if not pool:
        # The caller normally hands the pool in, taken from DexScreener, which
        # has no meaningful rate limit. Asking GeckoTerminal for it too would
        # spend half of a two-call budget on something already known.
        found = pools_for(mint)
        if not found:
            raise CandlesUnavailable(
                "GeckoTerminal is rate limiting us and no pool is known for this coin yet. "
                "This clears on its own within the minute."
                if throttled()
                else "Nothing has indexed a market for this coin yet, so there are no candles to draw."
            )
        pool = found[0]["address"]
        dex = found[0]["dex"]

    source = SOURCE[timeframe]
    span = TIMEFRAMES[timeframe][2] // TIMEFRAMES[source][2]
    bars, taken, stale = _fetch(pool, source, limit * max(1, span))

    if not bars:
        # The asked-for source was refused. Anything finer already in hand can
        # still be rolled up into the bars the reader wanted.
        for finer in ("1m", "1h"):
            if TIMEFRAMES[finer][2] < TIMEFRAMES[timeframe][2]:
                cached_finer = _bars.get(f"{pool}:{finer}")
                if cached_finer:
                    bars, taken, stale = cached_finer[1]["bars"], cached_finer[0], True
                    source = finer
                    break

    if not bars:
        raise CandlesUnavailable(
            "GeckoTerminal refused the candle call and nothing is cached for this pair yet. "
            "Its free tier allows about two calls before it blocks; this clears on its own."
        )

    if source != timeframe:
        bars = _roll(bars, TIMEFRAMES[timeframe][2])

    return Series(mint, pool, dex, timeframe, bars[-limit:], taken, stale)
