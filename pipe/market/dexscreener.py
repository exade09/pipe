from __future__ import annotations

"""
Market data and token images.

DexScreener indexes Solana under the id "solana". It gives price, liquidity,
volume and buy/sell counts across four windows, and `info.imageUrl`, which is
one of the two places the avatars in the feed come from. No key, no auth.

What it does not give is the first minutes of a coin's life: a pair has to be
indexed before it appears, and a coin still on the bonding curve has no pair
at all. That gap is exactly what pump.fun covers, which is why this terminal
reads both and treats pump.fun as the source of truth for existence and
DexScreener as the source for price.
"""

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pipe.config import DEXSCREENER_BASE, DEXSCREENER_CHAIN, user_agent

# The endpoint takes up to 30 comma-separated addresses per call.
BATCH = 30


@dataclass
class Market:
    token: str
    pair_address: str = ""
    dex: str = ""
    price_usd: float = 0.0
    price_native: float = 0.0
    liquidity_usd: float = 0.0
    liquidity_quote: float = 0.0
    fdv: float = 0.0
    market_cap: float = 0.0
    volume_h24: float = 0.0
    volume_h1: float = 0.0
    volume_m5: float = 0.0
    buys_h1: int = 0
    sells_h1: int = 0
    change_m5: float = 0.0
    change_h1: float = 0.0
    change_h24: float = 0.0
    created_at_ms: int = 0
    image_url: str = ""
    header_url: str = ""
    websites: list[str] = None  # type: ignore[assignment]
    socials: list[str] = None  # type: ignore[assignment]
    quote_symbol: str = ""

    def __post_init__(self) -> None:
        if self.websites is None:
            self.websites = []
        if self.socials is None:
            self.socials = []


def _get(url: str, timeout: int = 12) -> Any:
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": user_agent()},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        # A market-data outage must not take the feed down. Callers get
        # nothing for those tokens and the chain figures still render.
        return None


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _best_pair(pairs: list[dict]) -> dict | None:
    """A token can have several pairs. The deepest one is the real market."""
    usable = [p for p in pairs if p.get("chainId") == DEXSCREENER_CHAIN]
    if not usable:
        return None
    return max(usable, key=lambda p: _num((p.get("liquidity") or {}).get("usd")))


def _to_market(token: str, pair: dict) -> Market:
    liq = pair.get("liquidity") or {}
    vol = pair.get("volume") or {}
    chg = pair.get("priceChange") or {}
    txns = (pair.get("txns") or {}).get("h1") or {}
    info = pair.get("info") or {}
    return Market(
        token=token,
        pair_address=pair.get("pairAddress", ""),
        dex=pair.get("dexId", ""),
        price_usd=_num(pair.get("priceUsd")),
        price_native=_num(pair.get("priceNative")),
        liquidity_usd=_num(liq.get("usd")),
        liquidity_quote=_num(liq.get("quote")),
        fdv=_num(pair.get("fdv")),
        market_cap=_num(pair.get("marketCap")),
        volume_h24=_num(vol.get("h24")),
        volume_h1=_num(vol.get("h1")),
        volume_m5=_num(vol.get("m5")),
        buys_h1=int(txns.get("buys") or 0),
        sells_h1=int(txns.get("sells") or 0),
        change_m5=_num(chg.get("m5")),
        change_h1=_num(chg.get("h1")),
        change_h24=_num(chg.get("h24")),
        created_at_ms=int(pair.get("pairCreatedAt") or 0),
        image_url=info.get("imageUrl") or "",
        header_url=info.get("header") or "",
        websites=[w.get("url", "") for w in (info.get("websites") or []) if w.get("url")],
        socials=[s.get("url", "") for s in (info.get("socials") or []) if s.get("url")],
        quote_symbol=(pair.get("quoteToken") or {}).get("symbol", ""),
    )


def markets_for(addresses: list[str]) -> dict[str, Market]:
    """
    Market rows keyed by mint, exactly as given. Coins DexScreener has not
    indexed yet are simply absent — the normal state for anything still on the
    curve, not an error.
    """
    # Solana addresses are base58 and case sensitive. The EVM version of this
    # file lowercased every key, which silently matched nothing here: every
    # coin came back "no pool indexed", including migrated ones with millions
    # in market cap. Case is preserved end to end.
    out: dict[str, Market] = {}
    unique = [a for a in dict.fromkeys(addresses) if a]
    for start in range(0, len(unique), BATCH):
        chunk = unique[start : start + BATCH]
        url = f"{DEXSCREENER_BASE}/tokens/v1/{DEXSCREENER_CHAIN}/{','.join(chunk)}"
        data = _get(url)
        pairs = data if isinstance(data, list) else (data or {}).get("pairs") or []
        grouped: dict[str, list[dict]] = {}
        for pair in pairs:
            base = (pair.get("baseToken") or {}).get("address") or ""
            if base:
                grouped.setdefault(base, []).append(pair)
        for address in chunk:
            best = _best_pair(grouped.get(address, []))
            if best:
                out[address] = _to_market(address, best)
    return out


def market_for(address: str) -> Market | None:
    return markets_for([address]).get(address)
