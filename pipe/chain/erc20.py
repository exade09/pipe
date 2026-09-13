from __future__ import annotations

"""
Token metadata, read from the contract rather than from anybody's index.

Names and symbols are attacker-controlled strings. They are decoded here and
sanitised at the edge before they reach a browser; nothing in this module
trusts its own output.
"""

import time
from dataclasses import dataclass

from eth_utils import keccak

from pipe.chain.rpc import RpcClient

TRANSFER_TOPIC = "0x" + keccak(text="Transfer(address,address,uint256)").hex()

SEL_NAME = "0x" + keccak(text="name()")[:4].hex()
SEL_SYMBOL = "0x" + keccak(text="symbol()")[:4].hex()
SEL_DECIMALS = "0x" + keccak(text="decimals()")[:4].hex()
SEL_SUPPLY = "0x" + keccak(text="totalSupply()")[:4].hex()


@dataclass
class TokenMeta:
    address: str
    name: str
    symbol: str
    decimals: int
    total_supply: int


def _decode_string(raw: str | None) -> str:
    """
    Handles both the ABI string encoding and the older fixed bytes32 form,
    because both are in the wild and a token that returns bytes32 is not a
    reason to show an empty row.
    """
    if not raw or raw == "0x":
        return ""
    body = raw[2:]
    if len(body) >= 128:
        try:
            length = int(body[64:128], 16)
            if 0 < length <= 256 and len(body) >= 128 + length * 2:
                return bytes.fromhex(body[128 : 128 + length * 2]).decode("utf-8", "replace").strip()
        except ValueError:
            pass
    try:
        return bytes.fromhex(body[:64]).rstrip(b"\x00").decode("utf-8", "replace").strip()
    except ValueError:
        return ""


def _decode_uint(raw: str | None) -> int:
    if not raw or raw == "0x":
        return 0
    try:
        return int(raw, 16)
    except ValueError:
        return 0


# Four calls per token, and the node's batch ceiling was measured rather than
# guessed: 60 calls in one batch succeed, 80 come back 429. Twelve tokens is
# 48 calls, which leaves room for the limit to be lower on a busy node.
TOKENS_PER_BATCH = 12
# The ceiling is per batch, but sending them back to back still trips a rate
# limit. A short pause between chunks costs less than a retry does.
CHUNK_PAUSE_SECONDS = 0.12


def metadata_many(client: RpcClient, addresses: list[str]) -> dict[str, TokenMeta]:
    """
    Four calls per token, batched in chunks. A chunk the node refuses is
    skipped rather than raised: one unreadable group must not cost the whole
    page, and the rows it covers still render with the chain data we already
    have.
    """
    out: dict[str, TokenMeta] = {}
    for start in range(0, len(addresses), TOKENS_PER_BATCH):
        if start:
            time.sleep(CHUNK_PAUSE_SECONDS)
        chunk = addresses[start : start + TOKENS_PER_BATCH]
        calls: list[tuple[str, list]] = []
        for address in chunk:
            for selector in (SEL_NAME, SEL_SYMBOL, SEL_DECIMALS, SEL_SUPPLY):
                calls.append(("eth_call", [{"to": address, "data": selector}, "latest"]))
        try:
            results = client.batch(calls)
        except Exception:
            continue
        for index, address in enumerate(chunk):
            base = index * 4
            decimals = _decode_uint(results[base + 2])
            out[address.lower()] = TokenMeta(
                address=address.lower(),
                name=_decode_string(results[base]),
                symbol=_decode_string(results[base + 1]),
                decimals=decimals if 0 < decimals <= 36 else 18,
                total_supply=_decode_uint(results[base + 3]),
            )
    return out
