from __future__ import annotations

"""
Everything about the chain this terminal reads, in one place.

All of it is overridable by environment variable, because the defaults are
facts about a network that can change its endpoints without telling us, and a
wrong constant compiled into a build is the slowest kind of outage to
diagnose.
"""

import os

# ---------------------------------------------------------------- solana

# The public endpoint answers getAccountInfo, getTokenSupply and getSlot
# without a key. It refuses getTokenLargestAccounts with 429, and so do the
# other free endpoints — ankr and publicnode answer 403, drpc answers 400.
# Holders therefore need a paid or keyed RPC; everything else does not.
DEFAULT_RPC = "https://api.mainnet-beta.solana.com"

# Helius is the usual answer for the holder call. With a key set, the terminal
# reads distributions and draws the bubble map; without one it says so rather
# than drawing a map from nothing.
HELIUS_TEMPLATE = "https://mainnet.helius-rpc.com/?api-key={key}"

# pump.fun is where tokens are born on this chain, so its coin feed is the
# discovery feed the way the Pons log was on Robinhood Chain. The older
# frontend-api host answers 530; v3 works, and only with a browser-shaped
# User-Agent.
PUMPFUN_BASE = "https://frontend-api-v3.pump.fun"

# Migration threshold. pump.fun moves a coin to a real pool once the curve has
# taken roughly this much SOL, and `complete` on the coin is the authoritative
# flag — this number only drives the progress bar before that flips.
CURVE_TARGET_SOL = 85.0
LAMPORTS = 1_000_000_000

DEXSCREENER_BASE = "https://api.dexscreener.com"
DEXSCREENER_CHAIN = "solana"

# The two accounts that make a mint dangerous, and the values that make it
# safe. Both are read straight off the mint account.
SAFE_AUTHORITY = None

SYSTEM_PROGRAM = "11111111111111111111111111111111"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def rpc_url() -> str:
    """
    A keyed endpoint when one is configured, the public one otherwise. The
    difference is visible in the product: only the keyed path can read
    holders.
    """
    explicit = (os.getenv("SOLANA_RPC_URL") or "").strip()
    if explicit:
        return explicit
    key = (os.getenv("HELIUS_API_KEY") or "").strip()
    if key:
        return HELIUS_TEMPLATE.format(key=key)
    return DEFAULT_RPC


def holders_available() -> bool:
    return bool((os.getenv("SOLANA_RPC_URL") or os.getenv("HELIUS_API_KEY") or "").strip())


def pumpfun_base() -> str:
    return (os.getenv("PUMPFUN_BASE") or PUMPFUN_BASE).strip() or PUMPFUN_BASE


def database_url() -> str:
    """Empty means "run without a database", which the API routes support."""
    for name in ("DATABASE_URL", "POSTGRES_URL", "NEON_DATABASE_URL"):
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def user_agent() -> str:
    return (os.getenv("PIPE_USER_AGENT") or BROWSER_UA).strip()
