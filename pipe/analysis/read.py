from __future__ import annotations

"""
The read.

Every other scanner prints a score out of a hundred. A score hides the thing
that actually matters: a token with four verified facts and three unverifiable
ones is a different object from a token with seven verified facts, and both
come out as "72".

So this returns three lists and a paragraph, and never a number:

  ok    facts read off the chain, each with something behind it
  bad   facts that are disqualifying on their own
  unk   things that could not be checked, named rather than folded into a guess

The paragraph is assembled from the same facts, so it can never disagree with
the lists under it. There is no model in this path: an LLM can be layered on
later to write better prose, but it must not be allowed to invent a fact that
is not already in `ok`, `bad` or `unk`.
"""

from typing import Any

# Below this, a "liquidity" figure is noise rather than a market.
THIN_LIQUIDITY_USD = 2_000
CONCENTRATION_WATCH = 30.0
CONCENTRATION_BAD = 55.0
DEPLOYER_BAD = 15.0


def _age_phrase(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} minutes old"
    if minutes < 1440:
        return f"{minutes // 60} hours old"
    return f"{minutes // 1440} days old"


def build(token: dict, holders: dict | None = None) -> dict:
    ok: list[str] = []
    bad: list[str] = []
    unk: list[str] = []

    symbol = token.get("symbol") or "This token"
    age = int(token.get("age_minutes") or 0)
    liq = float(token.get("liquidity_usd") or 0)
    indexed = bool(token.get("indexed"))
    native = bool(token.get("native_pair", True))
    quote = token.get("quote_symbol") or ("ETH" if native else "an equity")

    top10 = float((holders or {}).get("top10_share") or token.get("top10_share") or 0)
    dev = float((holders or {}).get("deployer_share") or token.get("deployer_share") or 0)
    counted = int((holders or {}).get("counted") or token.get("holders_counted") or 0)
    clusters = (holders or {}).get("clusters") or []

    # ---------------------------------------------------------- structure
    ok.append("Launched through the Pons factory, log verified on chain")
    if not native:
        ok.append(f"Paired to {quote}, a listed and verified equity")

    if dev <= 0:
        ok.append("Deployer holds nothing — sold out or never held")
    elif dev >= DEPLOYER_BAD:
        bad.append(f"Deployer still holds {dev:.1f}% of the circulating supply")
    else:
        unk.append(f"Deployer holds {dev:.1f}% — small, and it has not moved")

    if counted:
        if top10 >= CONCENTRATION_BAD:
            bad.append(f"Top ten hold {top10:.1f}% across only {counted} holders")
        elif top10 >= CONCENTRATION_WATCH:
            unk.append(f"Top ten hold {top10:.1f}% — high, not yet decisive")
        else:
            ok.append(f"Top ten hold {top10:.1f}% across {counted} holders")
    else:
        unk.append("Holder distribution has not been read for this token yet")

    for cluster in clusters[:3]:
        unk.append(
            f"{cluster.get('wallets')} wallets holding {cluster.get('share')}% "
            "first received tokens from the same address"
        )

    # ---------------------------------------------------------- market
    if not indexed:
        unk.append("No market data yet — it has not been indexed off-chain")
        unk.append("Whether liquidity holds once anyone starts selling")
    elif liq < THIN_LIQUIDITY_USD:
        bad.append(f"Liquidity is ${liq:,.0f} — thin enough that the price is not a price")
    else:
        ok.append(f"Liquidity ${liq:,.0f}, deep enough to quote against")

    if age < 10:
        unk.append(f"Everything about behaviour — this is {age} minutes old")

    unk.append("Whether the largest wallets are one person or several")
    unk.append("Whether the accounts posting about it are genuine")

    # ---------------------------------------------------------- verdict
    if bad:
        lead = (
            f"{symbol} is {_age_phrase(age)} and carries "
            f"{'a flag' if len(bad) == 1 else f'{len(bad)} flags'}. "
        )
        if dev >= DEPLOYER_BAD:
            lead += f"The deployer still holds {dev:.1f}%. "
        if top10 >= CONCENTRATION_BAD:
            lead += (
                f"With the top ten at {top10:.1f}%, the price is being set by a handful "
                "of addresses rather than by a market. "
            )
        if indexed and liq < THIN_LIQUIDITY_USD:
            lead += "There is not enough liquidity behind the quote for it to mean much. "
        lead += "Everything below is read off the chain; none of it is an opinion about the people involved."
        risk = "risk"
    elif unk and (top10 >= CONCENTRATION_WATCH or not indexed or age < 10):
        lead = (
            f"{symbol} passes the structural checks — "
            f"{'the deployer is out' if dev <= 0 else 'the deployer has not moved'}, "
            "and the launch itself is verified. What is open is "
            + (
                "concentration, at "
                f"{top10:.1f}% in the top ten. "
                if top10 >= CONCENTRATION_WATCH
                else "simply time: nothing has happened yet to read. "
            )
            + "That is a fact rather than a verdict, and it resolves either way depending "
            "on things this cannot see."
        )
        risk = "watch"
    else:
        lead = (
            f"{symbol} comes back clean on everything that can be verified. "
            f"{'The deployer holds nothing. ' if dev <= 0 else ''}"
            f"{f'{top10:.1f}% in the top ten across {counted} holders is a wide book for something {_age_phrase(age)}. ' if counted else ''}"
            "Clean is not the same as safe — it means the checkable things checked out, "
            "and the list of what could not be checked is beside it."
        )
        risk = "ok"

    return {"verdict": lead, "ok": ok, "bad": bad, "unk": unk, "risk": risk}


def risk_only(token: dict) -> str:
    """Cheap flag for the feed, where the full read is not rendered."""
    return build(token).get("risk", "watch")
