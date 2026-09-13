from __future__ import annotations

"""
Holder distribution and the bubble map, computed from Transfer logs.

The explorer for this chain sits behind bot protection and answers 403 to
anything that is not a browser, so its holder endpoint is unavailable to a
server. That turns out not to matter: tokens here are minutes to hours old,
and replaying their whole Transfer history is a handful of logs. A token
twenty minutes into its life took four logs and under half a second.

Two exclusions matter and are deliberate:
  · the curve holds every token that has not been bought yet, and counting it
    as a holder makes every new launch look like a 96% rug
  · the zero and dead addresses are burns, not people
"""

from dataclasses import dataclass, field

from pipe.chain.erc20 import TRANSFER_TOPIC
from pipe.chain.rpc import RpcClient
from pipe.config import DEAD_ADDRESS, ZERO_ADDRESS


@dataclass
class Holder:
    address: str
    balance: int
    share: float = 0.0
    first_block: int = 0
    # The address this wallet received its first tokens from, ignoring the
    # curve. Wallets sharing one of these are grouped, because a distribution
    # to many wallets from one source is the shape worth seeing.
    source: str = ""
    cluster: int = -1
    is_deployer: bool = False


@dataclass
class Distribution:
    token: str
    holders: list[Holder] = field(default_factory=list)
    counted: int = 0
    circulating: int = 0
    top10_share: float = 0.0
    deployer_share: float = 0.0
    clusters: list[dict] = field(default_factory=list)
    logs_read: int = 0
    complete: bool = True


def distribution(
    client: RpcClient,
    *,
    token: str,
    curve: str,
    deployer: str,
    from_block: int,
    to_block: int | None = None,
    limit: int = 60,
) -> Distribution:
    token = token.lower()
    curve = (curve or "").lower()
    deployer = (deployer or "").lower()
    head = to_block if to_block is not None else client.block_number()

    logs = client.get_logs(
        address=token,
        topics=[TRANSFER_TOPIC],
        from_block=from_block,
        to_block=head,
    )

    balances: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    source: dict[str, str] = {}

    for log in logs:
        topics = log.get("topics") or []
        if len(topics) < 3:
            continue
        sender = "0x" + str(topics[1])[-40:].lower()
        receiver = "0x" + str(topics[2])[-40:].lower()
        try:
            value = int(log.get("data") or "0x0", 16)
        except ValueError:
            continue
        block = int(log["blockNumber"], 16)

        balances[sender] = balances.get(sender, 0) - value
        balances[receiver] = balances.get(receiver, 0) + value
        if receiver not in first_seen:
            first_seen[receiver] = block
            # Where the tokens actually came from. Buying on the curve is the
            # normal path and says nothing, so it is not recorded as a source.
            if sender not in (curve, ZERO_ADDRESS):
                source[receiver] = sender

    ignored = {curve, ZERO_ADDRESS, DEAD_ADDRESS, ""}
    people = {
        address: amount
        for address, amount in balances.items()
        if amount > 0 and address not in ignored
    }
    circulating = sum(people.values()) or 1

    ranked = sorted(people.items(), key=lambda item: -item[1])
    holders = [
        Holder(
            address=address,
            balance=amount,
            share=round(amount / circulating * 100, 4),
            first_block=first_seen.get(address, from_block),
            source=source.get(address, ""),
            is_deployer=(address == deployer),
        )
        for address, amount in ranked[:limit]
    ]

    # Group by shared source. A group of one is not a cluster, it is a wallet
    # that happened to be sent tokens once.
    by_source: dict[str, list[Holder]] = {}
    for holder in holders:
        if holder.source:
            by_source.setdefault(holder.source, []).append(holder)

    clusters: list[dict] = []
    for src, members in sorted(by_source.items(), key=lambda kv: -sum(h.share for h in kv[1])):
        if len(members) < 2:
            continue
        index = len(clusters)
        for holder in members:
            holder.cluster = index
        clusters.append(
            {
                "index": index,
                "source": src,
                "wallets": len(members),
                "share": round(sum(holder.share for holder in members), 3),
            }
        )

    top10 = round(sum(holder.share for holder in holders[:10]), 3)
    deployer_share = round(
        sum(holder.share for holder in holders if holder.is_deployer), 3
    )

    return Distribution(
        token=token,
        holders=holders,
        counted=len(people),
        circulating=circulating,
        top10_share=top10,
        deployer_share=deployer_share,
        clusters=clusters,
        logs_read=len(logs),
        complete=True,
    )
