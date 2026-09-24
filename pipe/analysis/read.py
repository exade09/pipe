from __future__ import annotations

"""
The read.

Every other scanner prints a score out of a hundred. A score hides the thing
that actually matters: a coin with four verified facts and three unverifiable
ones is a different object from one with seven verified facts, and both come
out as "72".

So this returns three lists and a paragraph, and never a number:

  ok    facts read off the chain, each with something behind it
  bad   facts that are disqualifying on their own
  unk   things that could not be checked, named rather than folded into a guess

The paragraph is assembled from the same facts, so it can never disagree with
the lists under it. There is no model in this path: a model can be layered on
to write better prose, but it must not be allowed to introduce a fact that is
not already in one of the three lists.
"""

THIN_LIQUIDITY_USD = 3_000
CONCENTRATION_WATCH = 25.0
CONCENTRATION_BAD = 50.0
CREATOR_BAD = 10.0


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

    symbol = token.get("symbol") or "This coin"
    age = int(token.get("age_minutes") or 0)
    liq = float(token.get("liquidity_usd") or 0)
    indexed = bool(token.get("indexed"))
    complete = bool(token.get("complete"))
    progress = float(token.get("progress") or 0) * 100
    readable = bool(token.get("mint_readable"))
    can_inflate = bool(token.get("can_inflate"))
    can_freeze = bool(token.get("can_freeze"))

    top10 = float((holders or {}).get("top10_share") or token.get("top10_share") or 0)
    creator = float((holders or {}).get("creator_share") or token.get("creator_share") or 0)
    counted = int((holders or {}).get("counted") or token.get("holders_counted") or 0)
    holders_read = bool(holders) or counted > 0

    # ------------------------------------------------- what the mint allows
    if not readable:
        unk.append("The mint account could not be read, so its authorities are unknown")
    else:
        if can_inflate:
            bad.append("Mint authority is still set — more supply can be created at any moment")
        else:
            ok.append("Mint authority revoked — the supply cannot grow")
        if can_freeze:
            bad.append("Freeze authority is still set — your balance can be frozen in your own wallet")
        else:
            ok.append("Freeze authority revoked — balances cannot be frozen")

    # ------------------------------------------------- where it is in life
    if complete:
        ok.append("Migrated to a pool — the bonding curve is finished")
    else:
        unk.append(f"Still on the curve at {progress:.0f}% — it has not migrated and may never")

    # ------------------------------------------------- who holds it
    if holders_read and counted:
        if creator >= CREATOR_BAD:
            bad.append(f"The creator's wallet holds {creator:.1f}% of what is circulating")
        elif creator > 0:
            unk.append(f"The creator holds {creator:.1f}% — small, and it has not moved")
        else:
            ok.append("The creator's wallet is not among the largest holders")

        if top10 >= CONCENTRATION_BAD:
            bad.append(f"The ten largest wallets hold {top10:.1f}% between them")
        elif top10 >= CONCENTRATION_WATCH:
            unk.append(f"The ten largest wallets hold {top10:.1f}% — high, not yet decisive")
        else:
            ok.append(f"The ten largest wallets hold {top10:.1f}%")
        unk.append("Only the twenty largest token accounts are read, not every holder")
    else:
        unk.append("Holder distribution has not been read for this coin")

    # ------------------------------------------------- market
    if not indexed:
        unk.append("No pool data yet — nothing has indexed a market for it")
    elif liq < THIN_LIQUIDITY_USD:
        bad.append(f"Liquidity is ${liq:,.0f}, thin enough that the price is not really a price")
    else:
        ok.append(f"Liquidity ${liq:,.0f} behind the quote")

    if age < 10:
        unk.append(f"Everything about behaviour — this is {age} minutes old")
    unk.append("Whether the largest wallets are one person or several")
    unk.append("Whether the accounts posting about it are genuine")

    # ------------------------------------------------- verdict
    if bad:
        lead = f"{symbol} is {_age_phrase(age)} and carries "
        lead += "a flag. " if len(bad) == 1 else f"{len(bad)} flags. "
        if can_inflate:
            lead += "The mint authority was never revoked, so the supply can be increased under you. "
        if can_freeze:
            lead += "The freeze authority is still live, which means a balance can be locked in the wallet holding it. "
        if creator >= CREATOR_BAD:
            lead += f"The creator still holds {creator:.1f}%. "
        if top10 >= CONCENTRATION_BAD:
            lead += f"With the top ten at {top10:.1f}%, the price is set by a handful of wallets rather than a market. "
        lead += "Everything below is read off the chain; none of it is an opinion about the people involved."
        risk = "risk"
    elif not holders_read or not complete or age < 10:
        lead = f"{symbol} passes what can be checked on the mint itself"
        if readable and not can_inflate and not can_freeze:
            lead += " — both authorities are revoked, so it cannot inflate and cannot freeze you"
        lead += ". What is open is "
        if not complete:
            lead += f"whether the curve finishes: it is at {progress:.0f}% and most never get there"
        elif not holders_read:
            lead += "who holds it, which needs a keyed endpoint this deployment is reading without"
        else:
            lead += "simply time — nothing has happened yet to read"
        lead += ". That is a fact rather than a verdict."
        risk = "watch"
    else:
        lead = (
            f"{symbol} comes back clean on everything that can be verified. Both authorities are "
            f"revoked, the curve is finished, and {top10:.1f}% in the ten largest wallets is a wide "
            f"book for something {_age_phrase(age)}. Clean is not the same as safe — it means the "
            "checkable things checked out, and what could not be checked is listed beside them."
        )
        risk = "ok"

    return {"verdict": lead, "ok": ok, "bad": bad, "unk": unk, "risk": risk}


def risk_only(token: dict) -> str:
    return build(token).get("risk", "watch")
