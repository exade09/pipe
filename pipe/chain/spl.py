from __future__ import annotations

"""
Mint state — the part of a Solana token that decides whether it can be turned
against you.

Two fields carry almost all of it, and both are readable without a key:

  mintAuthority    if this is set, more supply can be created at any moment
  freezeAuthority  if this is set, your balance can be frozen in your wallet

A coin where both are null cannot inflate and cannot freeze you. That is not
"safe" — it says nothing about who holds it or whether the pool survives — but
it is the floor, and a token that fails it fails before any other question is
worth asking.
"""

from dataclasses import dataclass

from pipe.chain.rpc import RpcClient


@dataclass
class MintInfo:
    mint: str
    decimals: int = 6
    supply: int = 0
    mint_authority: str | None = None
    freeze_authority: str | None = None
    program: str = ""
    readable: bool = False

    @property
    def can_inflate(self) -> bool:
        return bool(self.mint_authority)

    @property
    def can_freeze(self) -> bool:
        return bool(self.freeze_authority)


def _parse(mint: str, value: dict | None) -> MintInfo:
    if not value:
        return MintInfo(mint=mint)
    data = value.get("data") or {}
    parsed = data.get("parsed") or {}
    info = parsed.get("info") or {}
    if parsed.get("type") != "mint":
        # Not a mint account. Returning an unreadable row is the honest
        # answer; guessing decimals would corrupt every figure downstream.
        return MintInfo(mint=mint, program=data.get("program", ""))
    try:
        supply = int(info.get("supply") or 0)
    except (TypeError, ValueError):
        supply = 0
    return MintInfo(
        mint=mint,
        decimals=int(info.get("decimals") or 6),
        supply=supply,
        mint_authority=info.get("mintAuthority"),
        freeze_authority=info.get("freezeAuthority"),
        program=data.get("program", ""),
        readable=True,
    )


def mint_info(client: RpcClient, mint: str) -> MintInfo:
    return _parse(mint, client.account_info(mint))


def mint_info_many(client: RpcClient, mints: list[str]) -> dict[str, MintInfo]:
    """
    getMultipleAccounts takes a hundred keys per call, so a whole page of the
    feed is one or two round trips rather than one per row.
    """
    found = client.accounts_info(mints)
    return {mint: _parse(mint, found.get(mint)) for mint in mints}
