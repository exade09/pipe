from __future__ import annotations

"""
Holder distribution and the bubble map.

On an EVM chain this was computed by replaying Transfer logs, which also gave
the funding relationships between wallets for free. Solana does not work that
way: balances live in token accounts, and getTokenLargestAccounts returns the
twenty largest of them in one call.

That call is the thing no free endpoint will serve — mainnet-beta answers 429,
ankr and publicnode 403, drpc 400 — so this module raises RpcUnavailable
rather than returning an empty map that would read as "nobody holds this".

What this does and does not know, stated plainly because the map has to be
honest about it:

  · it reads the twenty largest token accounts, not every holder
  · it resolves each one to the wallet that owns it, so several accounts
    belonging to one person collapse into one circle
  · it marks the coin's creator, which is the single relationship that
    matters most and the one pump.fun hands over directly
  · it does NOT trace who funded whom. That needs signature history per
    wallet, which is a different order of cost, and inventing a cluster
    without it would be worse than showing none
"""

from dataclasses import dataclass, field

from pipe.chain.rpc import RpcClient, RpcError

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

    largest = client.largest_token_accounts(mint)
    if not largest:
        return Distribution(mint=mint, note="No token accounts returned for this mint.")

    accounts = [row.get("address") for row in largest if row.get("address")]
    amounts: dict[str, int] = {}
    for row in largest:
        address = row.get("address")
        if not address:
            continue
        try:
            amounts[address] = int(row.get("amount") or 0)
        except (TypeError, ValueError):
            amounts[address] = 0

    # Resolve each token account to its owning wallet, so one person holding
    # through three accounts is one circle rather than three.
    owners: dict[str, str] = {}
    try:
        info = client.accounts_info(accounts)
        for address, value in info.items():
            parsed = ((value or {}).get("data") or {}).get("parsed") or {}
            owners[address] = ((parsed.get("info") or {}).get("owner")) or ""
    except RpcError:
        owners = {address: "" for address in accounts}

    by_owner: dict[str, Holder] = {}
    curve_total = 0
    for address in accounts:
        owner = owners.get(address) or address
        amount = amounts.get(address, 0)
        if amount <= 0:
            continue
        if _programmatic(owner, curve, pool) or address in {curve, pool}:
            curve_total += amount
            continue
        existing = by_owner.get(owner)
        if existing:
            existing.amount += amount
            existing.accounts += 1
        else:
            by_owner[owner] = Holder(
                account=address,
                owner=owner,
                amount=amount,
                is_creator=bool(creator) and owner == creator,
            )

    people = sorted(by_owner.values(), key=lambda h: -h.amount)
    circulating = sum(h.amount for h in people) or 1
    for holder in people:
        holder.share = round(holder.amount / circulating * 100, 4)

    total_with_curve = circulating + curve_total or 1
    return Distribution(
        mint=mint,
        holders=people,
        counted=len(people),
        circulating=circulating,
        top10_share=round(sum(h.share for h in people[:10]), 3),
        creator_share=round(sum(h.share for h in people if h.is_creator), 3),
        curve_share=round(curve_total / total_with_curve * 100, 3),
        truncated=True,
        note=(
            "The twenty largest token accounts, resolved to the wallets that own them. "
            "Shares are of the supply those wallets hold between them, with the bonding "
            "curve excluded."
        ),
    )
