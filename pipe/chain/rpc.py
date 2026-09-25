from __future__ import annotations

"""
Solana JSON-RPC.

Two things here were learned by trying rather than by reading docs.

The public endpoint serves getAccountInfo, getTokenSupply and getSlot without
a key, which covers the security checks this terminal cares most about — a
mint's mint authority and freeze authority are the two facts that decide
whether the supply can grow under you or your balance can be frozen.

It refuses getTokenLargestAccounts with 429, and so does every other free
endpoint tried: ankr and publicnode answer 403, drpc answers 400.

That looked like the end of holder data without a key, and it was not. The
same endpoint serves getProgramAccounts against the token program, filtered to
one mint, and that returns every token account rather than the twenty largest
— measured at 49,358 accounts in 2.2 seconds for a live pump.fun coin. Asking
for a 40 byte slice of each account instead of the parsed whole keeps the
answer to the two fields a distribution needs, the owner and the amount.

It has one limit worth naming: a mint with millions of accounts, USDC for
instance, comes back INTERNAL_ERROR because the answer is too large to build.
No coin this terminal is pointed at is anywhere near that, and the refusal is
reported rather than swallowed.
"""

import base64
import json
import struct
import time
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pipe.config import TOKEN_2022_PROGRAM, TOKEN_PROGRAM, rpc_url, user_agent

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58(raw: bytes) -> str:
    """
    Solana addresses come back as raw bytes when the account is read as a
    slice rather than parsed, so the encoding has to happen here. Leading zero
    bytes are leading ones, which is the part every naive implementation
    drops.
    """
    number = int.from_bytes(raw, "big")
    out = ""
    while number:
        number, rest = divmod(number, 58)
        out = _B58[rest] + out
    pad = len(raw) - len(raw.lstrip(bytes([0])))
    return "1" * pad + out


class RpcError(RuntimeError):
    pass


class RpcUnavailable(RpcError):
    """The call needs an endpoint this deployment does not have."""


class RpcClient:
    def __init__(self, url: str | None = None, *, timeout: int = 25, retries: int = 2) -> None:
        self.url = url or rpc_url()
        self.timeout = timeout
        self.retries = retries
        self._id = 0

    # ------------------------------------------------------------ transport

    def _post(self, payload: Any) -> Any:
        body = json.dumps(payload).encode("utf-8")
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            request = Request(
                self.url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": user_agent(),
                },
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                last = exc
                if exc.code in (429, 502, 503, 504) and attempt < self.retries:
                    # 429 on the public endpoint is a real ceiling, not a
                    # hiccup, so the pause is long enough to be worth taking.
                    time.sleep((1.2 if exc.code == 429 else 0.4) * (attempt + 1))
                    continue
                raise RpcError(f"rpc http {exc.code}") from exc
            except (URLError, TimeoutError) as exc:
                last = exc
                if attempt < self.retries:
                    time.sleep(0.4 * (attempt + 1))
                    continue
        raise RpcError(f"rpc unreachable: {last}")

    def call(self, method: str, params: list[Any] | None = None) -> Any:
        self._id += 1
        out = self._post({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or []})
        if isinstance(out, dict) and "error" in out:
            raise RpcError(f"{method}: {out['error']}")
        return out["result"]

    def batch(self, calls: Iterable[tuple[str, list[Any]]]) -> list[Any]:
        """
        One round trip for many calls, results in request order. A failure
        inside the batch comes back as None rather than raising: one
        unreadable mint must not cost a page of forty.
        """
        items = list(calls)
        if not items:
            return []
        payload = []
        for method, params in items:
            self._id += 1
            payload.append({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params})
        out = self._post(payload)
        if not isinstance(out, list):
            raise RpcError("batch response was not a list")
        by_id = {item.get("id"): item for item in out}
        results = []
        for entry in payload:
            item = by_id.get(entry["id"]) or {}
            results.append(None if "error" in item else item.get("result"))
        return results

    # ------------------------------------------------------------ helpers

    def slot(self) -> int:
        return int(self.call("getSlot") or 0)

    def healthy(self) -> bool:
        try:
            return self.call("getHealth") == "ok"
        except RpcError:
            return False

    def account_info(self, address: str) -> dict | None:
        out = self.call("getAccountInfo", [address, {"encoding": "jsonParsed"}])
        return (out or {}).get("value")

    def accounts_info(self, addresses: list[str]) -> dict[str, dict | None]:
        """getMultipleAccounts takes up to 100 keys, so pages of 100."""
        found: dict[str, dict | None] = {}
        for start in range(0, len(addresses), 100):
            chunk = addresses[start : start + 100]
            try:
                out = self.call("getMultipleAccounts", [chunk, {"encoding": "jsonParsed"}])
            except RpcError:
                for address in chunk:
                    found[address] = None
                continue
            values = (out or {}).get("value") or []
            for address, value in zip(chunk, values):
                found[address] = value
        return found

    def token_supply(self, mint: str) -> dict | None:
        out = self.call("getTokenSupply", [mint])
        return (out or {}).get("value")

    def sol_balance(self, owner: str) -> int:
        out = self.call("getBalance", [owner])
        return int((out or {}).get("value") or 0)

    def token_balance(self, owner: str, mint: str) -> dict:
        """
        What the wallet holds of one mint. getTokenAccountsByOwner is served by
        the public endpoint, unlike the holder call, because it is scoped to a
        single owner rather than to the whole mint.

        A wallet can hold the same mint in more than one account, so the
        balances are summed rather than the first one taken.
        """
        out = self.call(
            "getTokenAccountsByOwner",
            [owner, {"mint": mint}, {"encoding": "jsonParsed"}],
        )
        amount = 0
        decimals = 0
        for item in ((out or {}).get("value") or []):
            info = (((item.get("account") or {}).get("data") or {}).get("parsed") or {}).get("info") or {}
            token = info.get("tokenAmount") or {}
            try:
                amount += int(token.get("amount") or 0)
                decimals = int(token.get("decimals") or decimals)
            except (TypeError, ValueError):
                continue
        return {"amount": amount, "decimals": decimals}

    def largest_token_accounts(self, mint: str) -> list[dict]:
        """Kept for callers that want the twenty largest and nothing more."""
        out = self.call("getTokenLargestAccounts", [mint])
        return (out or {}).get("value") or []

    def mint_program(self, mint: str) -> str:
        """
        Which token program owns this mint. Asking is cheap and guessing is
        the difference between every holder and none of them.
        """
        info = self.account_info(mint) or {}
        owner = info.get("owner") or ""
        return owner if owner in (TOKEN_PROGRAM, TOKEN_2022_PROGRAM) else TOKEN_PROGRAM

    def token_accounts_by_mint(self, mint: str, program: str = "") -> list[tuple[str, int]]:
        """
        Every token account holding this mint, as (owner, amount).

        A token account carries the mint at offset 0 and the owner and amount
        in the 40 bytes at offset 32, so the filter is the mint and the slice
        is those 40 bytes. Nothing else is fetched: the parsed form of the same
        query is thirteen megabytes where this is a fraction of it, and no
        other field belongs in a distribution.

        There is deliberately no size filter. Token-2022 accounts carry
        extensions and run past the classic 165 bytes, and filtering on that
        number drops all but a handful of them - checked against a live mint,
        where the size filter found 16 accounts and no filter found 5,740
        whose balances sum to exactly the reported supply.
        """
        out = self.call(
            "getProgramAccounts",
            [
                program or self.mint_program(mint),
                {
                    "encoding": "base64",
                    "dataSlice": {"offset": 32, "length": 40},
                    "filters": [{"memcmp": {"offset": 0, "bytes": mint}}],
                },
            ],
        )
        rows: list[tuple[str, int]] = []
        for item in out or []:
            data = ((item or {}).get("account") or {}).get("data")
            blob = data[0] if isinstance(data, list) and data else None
            if not blob:
                continue
            try:
                raw = base64.b64decode(blob)
                if len(raw) < 40:
                    continue
                rows.append((base58(raw[0:32]), struct.unpack_from("<Q", raw, 32)[0]))
            except (ValueError, struct.error):
                continue
        return rows
