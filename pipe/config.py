from __future__ import annotations

"""
Everything about the chain this terminal reads, in one place.

All of it is overridable by environment variable, because the defaults are
facts about a network that can change its endpoints without telling us, and a
wrong constant compiled into a build is the slowest kind of outage to
diagnose.
"""

import os

# Robinhood Chain mainnet. The RPC refuses requests without a User-Agent with
# a bare 403 and no body, which reads exactly like the node being down. Every
# request in pipe.chain.rpc sets one.
DEFAULT_RPC = "https://rpc.mainnet.chain.robinhood.com"
CHAIN_ID = 4663

# Pons. Every token on this chain that anyone trades was launched here, so the
# TokenLaunched log is the whole discovery feed.
DEFAULT_FACTORY = "0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e"

# Measured, not assumed: ~0.1s per block, so a minute is roughly 600 blocks
# and an hour is roughly 36,000. Every range calculation in the indexer is
# derived from this rather than from a guess about "recent".
BLOCK_SECONDS = 0.1

# The node accepts wide eth_getLogs ranges, but a wide range on a chain this
# fast returns a lot. 10k blocks is about seventeen minutes of history.
MAX_LOG_RANGE = 10_000

DEXSCREENER_BASE = "https://api.dexscreener.com"
# DexScreener's own id for this network. Confirmed against a live response,
# not inferred from the name.
DEXSCREENER_CHAIN = "robinhood"

ZERO_ADDRESS = "0x" + "0" * 40
DEAD_ADDRESS = "0x" + "0" * 39 + "1"


def rpc_url() -> str:
    return (os.getenv("ROBINHOOD_RPC_URL") or DEFAULT_RPC).strip() or DEFAULT_RPC


def factory_address() -> str:
    return (os.getenv("PONS_FACTORY") or DEFAULT_FACTORY).strip() or DEFAULT_FACTORY


def database_url() -> str:
    """Empty means "run without a database", which the API routes support."""
    for name in ("DATABASE_URL", "POSTGRES_URL", "NEON_DATABASE_URL"):
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def user_agent() -> str:
    return (os.getenv("PIPE_USER_AGENT") or "pipe-terminal/0.1").strip()


def blocks_for_minutes(minutes: float) -> int:
    return max(1, int(minutes * 60 / BLOCK_SECONDS))
