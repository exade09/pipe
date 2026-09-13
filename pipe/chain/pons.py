from __future__ import annotations

"""
The discovery feed.

Every tradable token on this chain is launched through the Pons factory, and
every launch emits one TokenLaunched log. That log is the entire "new pairs"
column: three indexed addresses and, in the data, the token it is paired
against.

Event shape was read off a live log rather than taken from an ABI file:
  topics[0]  keccak of the signature
  topics[1]  token
  topics[2]  curve
  topics[3]  deployer
  data[0]    pair token — 0x0 means the native pair
  data[1]    uint256, meaning not yet established
  data[2]    uint256, meaning not yet established
The two trailing words are carried through untouched and never interpreted;
naming them would be inventing a fact.
"""

from dataclasses import dataclass
from typing import Any

from eth_utils import keccak

from pipe.chain.rpc import RpcClient
from pipe.config import ZERO_ADDRESS, factory_address

TOKEN_LAUNCHED_TOPIC = "0x" + keccak(
    text="TokenLaunched(address,address,address,address,uint256,uint256)"
).hex()


@dataclass(frozen=True)
class Launch:
    token: str
    curve: str
    deployer: str
    pair_token: str
    block: int
    tx: str
    log_index: int

    @property
    def native_pair(self) -> bool:
        return self.pair_token.lower() == ZERO_ADDRESS


def _addr(topic: str) -> str:
    return "0x" + str(topic)[-40:].lower()


def decode_launch(log: dict[str, Any]) -> Launch | None:
    topics = log.get("topics") or []
    if len(topics) < 4:
        return None
    data = (log.get("data") or "0x")[2:]
    pair = "0x" + data[24:64].lower() if len(data) >= 64 else ZERO_ADDRESS
    return Launch(
        token=_addr(topics[1]),
        curve=_addr(topics[2]),
        deployer=_addr(topics[3]),
        pair_token=pair,
        block=int(log["blockNumber"], 16),
        tx=log.get("transactionHash", ""),
        log_index=int(log.get("logIndex", "0x0"), 16),
    )


def launches_between(client: RpcClient, from_block: int, to_block: int) -> list[Launch]:
    """Newest first, which is the order the terminal shows them in."""
    logs = client.get_logs(
        address=factory_address(),
        topics=[TOKEN_LAUNCHED_TOPIC],
        from_block=from_block,
        to_block=to_block,
    )
    out = [decode_launch(log) for log in logs]
    found = [item for item in out if item is not None]
    found.sort(key=lambda item: (item.block, item.log_index), reverse=True)
    return found


def recent_launches(client: RpcClient, *, blocks: int = 6_000) -> list[Launch]:
    head = client.block_number()
    return launches_between(client, head - blocks, head)
