from __future__ import annotations

"""
Holder distribution and the bubble map.

getTokenLargestAccounts is the obvious call and no free endpoint will serve
it, which is where this module used to stop. getProgramAccounts against the
token program, filtered to one mint, is served — and it returns better data
than the call it stands in for: every token account rather than the twenty
largest, so the holder count is the real one and the shares are of the real
circulating supply rather than of the top twenty between them.

What this knows and does not know, stated plainly because the map has to be
honest about it:

  · it reads every token account for the mint, not a sample
  · it resolves each to the wallet that owns it, so one person holding
    through three accounts is one circle
  · it drops the bonding curve and the pool, which hold supply but are not
    people. counting the curve makes every new coin look like one wallet
    owns almost all of it
  · it marks the coin's creator, the single relationship that matters most
    and the one pump.fun hands over directly
  · it does NOT trace who funded whom. That needs signature history per
    wallet, which is a different order of cost, and inventing a cluster
    without it would be worse than drawing none
"""

from dataclasses import dataclass, field

from pipe.chain.rpc import RpcClient, RpcError

# How many wallets the map draws. The count above it is the real one; this is
# only what fits on screen as circles before they stop being distinguishable.
MAP_LIMIT = 80

# Accounts that hold supply but are not people. The curve holds everything
# nobody has bought yet; counting it makes every new coin look like one wallet
# owns 96% of it.
def _programmatic(owner: str, curve: str, pool: str) -> bool:
    return owner in {curve, pool} and bool(owner)


@dataclass
class Holder:
    account: str
    owner: str
    amount: int
    share: float = 0.0
    is_creator: bool = False
    is_curve: bool = False
    accounts: int = 1


@dataclass
class Distribution:
    mint: str
    holders: list[Holder] = field(default_factory=list)
    counted: int = 0
    circulating: int = 0
    top10_share: float = 0.0
    creator_share: float = 0.0
    curve_share: float = 0.0
    truncated: bool = True
    note: str = ""


def distribution(
    client: RpcClient,
    *,
    mint: str,
    creator: str = "",
    curve: str = "",
    pool: str = "",
) -> Distribution:
    creator = (creator or "").strip()
    curve = (curve or "").strip()
    pool = (pool or "").strip()

    rows = client.token_accounts_by_mint(mint)
    if not rows:
        return Distribution(
            mint=mint,
            truncated=False,
            note="No token accounts exist for this mint yet, so nobody holds it.",
        )

    by_owner: dict[str, Holder] = {}
    curve_total = 0
    for owner, amount in rows:
        if amount <= 0:
            continue
        if owner and owner in {curve, pool}:
            curve_total += amount
            continue
        existing = by_owner.get(owner)
        if existing:
            existing.amount += amount
            existing.accounts += 1
        else:
            by_owner[owner] = Holder(
                account=owner,
                owner=owner,
                amount=amount,
                is_creator=bool(creator) and owner == creator,
            )

    people = sorted(by_owner.values(), key=lambda h: -h.amount)
    circulating = sum(h.amount for h in people) or 1
    for holder in people:
        holder.share = round(holder.amount / circulating * 100, 4)

    total_with_curve = circulating + curve_total or 1
    drawn = people[:MAP_LIMIT]
    return Distribution(
        mint=mint,
        holders=drawn,
        counted=len(people),
        circulating=circulating,
        top10_share=round(sum(h.share for h in people[:10]), 3),
        creator_share=round(sum(h.share for h in people if h.is_creator), 3),
        curve_share=round(curve_total / total_with_curve * 100, 3),
        truncated=len(people) > len(drawn),
        note=(
            f"Every token account for this mint, read straight off the chain and resolved "
            f"to the {len(people):,} wallets that own them. Shares are of the supply those "
            f"wallets hold between them, with the bonding curve and the pool excluded."
            + (f" The map draws the largest {len(drawn)}." if len(people) > len(drawn) else "")
        ),
    )
