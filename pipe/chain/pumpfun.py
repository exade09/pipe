from __future__ import annotations

"""
The discovery feed.

On Robinhood Chain every token came out of one factory and every launch left a
log, so the chain itself was the feed. Solana has no such single door — coins
are born on pump.fun and graduate to a real pool — so the launch feed is
pump.fun's own coin list, ordered by creation.

Two things about that endpoint, both learned by trying:

  · the old frontend-api host answers 530. frontend-api-v3 works.
  · it wants a browser-shaped User-Agent. A library default gets nothing.

What comes back is richer than the Pons log was: the creator, the bonding
curve account, the reserves, and `complete`, which is the authoritative flag
for whether a coin has migrated. That is why this terminal can show the three
columns a Solana trader expects — new, filling, migrated — with each one
resting on a real field rather than on a guess about age.
"""

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pipe.config import CURVE_TARGET_SOL, LAMPORTS, pumpfun_base, user_agent


@dataclass
class Coin:
    mint: str
    name: str
    symbol: str
    creator: str
    created_ms: int
    complete: bool
    image_uri: str
    market_cap_usd: float
    market_cap_sol: float
    real_sol: float
    total_supply: int
    decimals: int
    bonding_curve: str
    pool_address: str
    reply_count: int
    nsfw: bool

    @property
    def progress(self) -> float:
        """
        0 to 1 toward migration, and `complete` is the only thing that reaches
        exactly 1.

        The reserve figure is not always denominated in SOL — pump.fun now
        carries coins with other quote mints — so a curve can read far past
        the threshold while still being open. Capping an incomplete curve
        below 1 keeps the bar honest instead of showing a full one next to a
        token that has not migrated.
        """
        if self.complete:
            return 1.0
        return max(0.0, min(0.99, self.real_sol / CURVE_TARGET_SOL))

    @property
    def stage(self) -> str:
        if self.complete:
            return "migrated"
        return "stretch" if self.progress >= 0.5 else "new"

    @property
    def age_minutes(self) -> int:
        """
        Unknown reads as zero rather than as fifty years. A coin assembled off
        the chain has no creation time, and dating it from the epoch put
        "20721d old" on the page.
        """
        import time as _t

        if self.created_ms <= 0:
            return 0
        return max(0, int((_t.time() * 1000 - self.created_ms) / 60000))


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clean(text: Any, limit: int = 64) -> str:
    """
    Names and symbols are written by whoever deployed the coin. Control
    characters come out here so nothing downstream has to remember to.
    """
    out = "".join(ch for ch in str(text or "") if ch.isprintable())
    return out.strip()[:limit]


def _get(path: str, params: dict | None = None, timeout: int = 15) -> Any:
    url = f"{pumpfun_base()}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": user_agent(),
            "Referer": "https://pump.fun/",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None


# pump.fun hands out image URLs on ipfs.io, and ipfs.io answers 403 to
# anything that is not a browser it likes — so every fresh coin in the feed
# rendered as a placeholder. The same CID served through pump's own pinata
# gateway comes back as the real jpeg, png or webp in under a second.
IPFS_IO = "https://ipfs.io/ipfs/"
IPFS_GATEWAY = "https://pump.mypinata.cloud/ipfs/"


def _image(uri: str) -> str:
    if not uri:
        return ""
    if "/ipfs/" in uri and uri.startswith(IPFS_IO):
        return IPFS_GATEWAY + uri.split("/ipfs/", 1)[1]
    return uri


def _to_coin(raw: dict) -> Coin | None:
    mint = raw.get("mint")
    if not mint:
        return None
    return Coin(
        mint=mint,
        name=_clean(raw.get("name")),
        symbol=_clean(raw.get("symbol"), 24),
        creator=raw.get("creator") or "",
        created_ms=int(raw.get("created_timestamp") or 0),
        complete=bool(raw.get("complete")),
        image_uri=_image(raw.get("image_uri") or ""),
        market_cap_usd=_num(raw.get("usd_market_cap")),
        market_cap_sol=_num(raw.get("market_cap")),
        real_sol=_num(raw.get("real_sol_reserves")) / LAMPORTS,
        total_supply=int(_num(raw.get("total_supply"))),
        decimals=int(raw.get("base_decimals") or 6),
        bonding_curve=raw.get("bonding_curve") or "",
        pool_address=raw.get("pool_address") or "",
        reply_count=int(raw.get("reply_count") or 0),
        nsfw=bool(raw.get("nsfw")),
    )


# Coins the list endpoint has handed us, kept so the page for one of them can
# be built when the per-coin endpoint will not answer. That endpoint 404s for
# the newest launches - the ones the list returned seconds earlier - and
# falling through to the chain alone costs the name, the symbol, the creator
# and the real curve position.
_seen: dict[str, Coin] = {}
_SEEN_LIMIT = 2000


def remembered(mint: str) -> Coin | None:
    return _seen.get(mint)


def _coins(params: dict) -> list[Coin]:
    raw = _get("/coins", params)
    if not isinstance(raw, list):
        return []
    out = [_to_coin(item) for item in raw if isinstance(item, dict)]
    coins = [coin for coin in out if coin is not None]
    for coin in coins:
        _seen[coin.mint] = coin
    if len(_seen) > _SEEN_LIMIT:
        for mint in list(_seen)[: len(_seen) - _SEEN_LIMIT]:
            _seen.pop(mint, None)
    return coins


def newest(limit: int = 60, offset: int = 0, include_nsfw: bool = False) -> list[Coin]:
    return _coins(
        {
            "offset": offset,
            "limit": min(limit, 100),
            "sort": "created_timestamp",
            "order": "DESC",
            "includeNsfw": str(bool(include_nsfw)).lower(),
        }
    )


def about_to_graduate(limit: int = 40) -> list[Coin]:
    """
    Coins closest to migration. Sorting by market cap among incomplete curves
    is what "final stretch" actually means — not age, which is the proxy a
    feed reaches for when it cannot see the curve.
    """
    coins = _coins(
        {
            "offset": 0,
            "limit": min(limit, 100),
            "sort": "market_cap",
            "order": "DESC",
            "includeNsfw": "false",
            # Without this the top of the market-cap list is entirely coins
            # that already migrated, and filtering afterwards leaves nothing.
            "complete": "false",
        }
    )
    # The feed carries records with a large market cap and zero reserves —
    # coins whose `complete` flag has not caught up, or which sit in a state
    # the reserve fields do not describe. They are not close to graduating in
    # any sense a reader would mean, so they are dropped rather than shown at
    # 0% above coins genuinely at the threshold.
    live = [coin for coin in coins if coin.real_sol > 0]
    live.sort(key=lambda coin: coin.real_sol, reverse=True)
    return live[:limit]


def migrated(limit: int = 40) -> list[Coin]:
    coins = _coins(
        {
            "offset": 0,
            "limit": min(limit * 3, 100),
            "sort": "last_trade_timestamp",
            "order": "DESC",
            "includeNsfw": "false",
        }
    )
    return [coin for coin in coins if coin.complete][:limit]


def one(mint: str) -> Coin | None:
    raw = _get(f"/coins/{mint}")
    if isinstance(raw, dict):
        coin = _to_coin(raw)
        if coin:
            _seen[coin.mint] = coin
            return coin
    return remembered(mint)
