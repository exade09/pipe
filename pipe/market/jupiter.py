from __future__ import annotations

"""
The swap.

Everything else in this terminal reads. This is the one module that helps the
reader act, and it is built so that the acting stays entirely with them: Jupiter
prices the route and builds the transaction, the browser hands that transaction
to the reader's own wallet, and the wallet is the only thing that ever signs.
No key, no custody, and nothing here can move a lamport on its own.

Jupiter's lite host needs no API key and routes pump.fun's own AMM alongside
Raydium, Orca, Meteora and the rest — which is why a single panel can trade a
coin while it is still on the curve and the same coin after it migrates,
without the reader having to know which of those two it is.

Two numbers the panel must show and this module therefore returns untouched:
the price impact Jupiter computed, and the minimum the reader receives if the
whole slippage tolerance is used. A swap UI that shows neither is showing a
price it cannot promise.
"""

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pipe.config import MAX_PRIORITY_LAMPORTS, WSOL_MINT, jupiter_base, user_agent


class JupiterError(RuntimeError):
    pass


@dataclass
class Quote:
    input_mint: str
    output_mint: str
    in_amount: int
    out_amount: int
    min_out_amount: int
    price_impact_pct: float
    slippage_bps: int
    route: list[str]
    raw: dict


def _call(path: str, params: dict | None = None, body: dict | None = None, timeout: int = 25) -> Any:
    url = f"{jupiter_base()}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        url,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": user_agent(),
        },
        method="POST" if data is not None else "GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = ""
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            detail = payload.get("error") or payload.get("message") or ""
        except Exception:
            pass
        if exc.code == 400 and detail:
            raise JupiterError(detail) from exc
        raise JupiterError(f"Jupiter answered {exc.code}. {detail}".strip()) from exc
    except (URLError, TimeoutError) as exc:
        raise JupiterError(f"Jupiter is unreachable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise JupiterError("Jupiter returned something that was not JSON.") from exc


def quote(
    input_mint: str,
    output_mint: str,
    amount: int,
    slippage_bps: int = 150,
) -> Quote:
    if amount <= 0:
        raise JupiterError("Amount must be above zero.")
    raw = _call(
        "/quote",
        {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": int(amount),
            "slippageBps": int(max(10, min(slippage_bps, 5000))),
            "restrictIntermediateTokens": "true",
        },
    )
    if not isinstance(raw, dict) or "outAmount" not in raw:
        raise JupiterError("No route for this pair. Nothing Jupiter knows about trades it yet.")
    try:
        impact = float(raw.get("priceImpactPct") or 0) * 100
    except (TypeError, ValueError):
        impact = 0.0
    return Quote(
        input_mint=input_mint,
        output_mint=output_mint,
        in_amount=int(raw.get("inAmount") or amount),
        out_amount=int(raw.get("outAmount") or 0),
        min_out_amount=int(raw.get("otherAmountThreshold") or 0),
        price_impact_pct=impact,
        slippage_bps=int(raw.get("slippageBps") or slippage_bps),
        route=[
            ((step.get("swapInfo") or {}).get("label") or "?")
            for step in (raw.get("routePlan") or [])
        ],
        raw=raw,
    )


def swap_transaction(quote_raw: dict, owner: str, priority_lamports: int = 1_000_000) -> dict:
    """
    The unsigned transaction, base64. It goes to the browser, the wallet signs
    it, and the wallet sends it — this process never holds a key and never
    submits anything.
    """
    if not owner:
        raise JupiterError("No wallet address.")
    payload = _call(
        "/swap",
        body={
            "quoteResponse": quote_raw,
            "userPublicKey": owner,
            "wrapAndUnwrapSol": True,
            "dynamicComputeUnitLimit": True,
            "prioritizationFeeLamports": {
                "priorityLevelWithMaxLamports": {
                    "maxLamports": int(max(0, min(priority_lamports, MAX_PRIORITY_LAMPORTS))),
                    "priorityLevel": "high",
                }
            },
        },
    )
    tx = (payload or {}).get("swapTransaction")
    if not tx:
        raise JupiterError("Jupiter built no transaction for that quote.")
    return {
        "transaction": tx,
        "last_valid_block_height": payload.get("lastValidBlockHeight"),
        "priority_lamports": payload.get("prioritizationFeeLamports"),
        "compute_unit_limit": payload.get("computeUnitLimit"),
    }


def sol_mint() -> str:
    return WSOL_MINT
