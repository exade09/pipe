from __future__ import annotations

"""
Solana JSON-RPC.

Two things here were learned by trying rather than by reading docs.

The public endpoint serves getAccountInfo, getTokenSupply and getSlot without
a key, which covers the security checks this terminal cares most about — a
mint's mint authority and freeze authority are the two facts that decide
whether the supply can grow under you or your balance can be frozen.

It refuses getTokenLargestAccounts with 429, and so does every other free
endpoint tried: ankr and publicnode answer 403, drpc answers 400. Holders are
therefore gated behind a keyed RPC, and the code says so out loud rather than
retrying into a wall.
"""

import json
import time
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pipe.config import holders_available, rpc_url, user_agent


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

    def largest_token_accounts(self, mint: str) -> list[dict]:
        """
        The holder call, and the one the free endpoints will not serve. It is
        refused loudly here so the caller can say "set a key" instead of
        showing an empty chart that looks like a token with no holders.
        """
        if not holders_available():
            raise RpcUnavailable(
                "Holder data needs a keyed RPC. Set HELIUS_API_KEY or SOLANA_RPC_URL."
            )
        out = self.call("getTokenLargestAccounts", [mint])
        return (out or {}).get("value") or []
