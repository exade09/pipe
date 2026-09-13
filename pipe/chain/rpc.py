from __future__ import annotations

"""
JSON-RPC against Robinhood Chain.

Two things here are not decoration. The User-Agent header is required: without
it the node answers 403 with an empty body, which is indistinguishable from
the endpoint being gone. And batching is required: blocks land every 0.1s, so
anything that reads per-token state one call at a time falls behind the chain
faster than it catches up.
"""

import json
import time
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pipe.config import MAX_LOG_RANGE, rpc_url, user_agent


class RpcError(RuntimeError):
    pass


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
                # 403 here almost always means the User-Agent was stripped by
                # something in the middle, not that we are rate limited.
                if exc.code in (429, 502, 503, 504) and attempt < self.retries:
                    # 429 needs real room, not a token pause: the node is
                    # telling us the batch was too big or too frequent.
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
        One round trip for many calls. Results come back in request order, and
        a failure inside the batch is returned as None rather than raised: a
        single unreadable token must not take down a page of forty.
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

    def block_number(self) -> int:
        return int(self.call("eth_blockNumber"), 16)

    def block_timestamp(self, number: int) -> int:
        block = self.call("eth_getBlockByNumber", [hex(number), False])
        return int(block["timestamp"], 16) if block else 0

    def get_code(self, address: str) -> str:
        return self.call("eth_getCode", [address, "latest"]) or "0x"

    def eth_call(self, to: str, data: str, *, frm: str | None = None) -> str:
        tx: dict[str, Any] = {"to": to, "data": data}
        if frm:
            tx["from"] = frm
        return self.call("eth_call", [tx, "latest"])

    def get_logs(
        self,
        *,
        address: str | list[str] | None,
        topics: list[Any],
        from_block: int,
        to_block: int,
    ) -> list[dict[str, Any]]:
        """
        Walks the range in MAX_LOG_RANGE slices. At 0.1s per block a naive
        "last 24 hours" is 864,000 blocks, so callers are expected to think
        about the window; this only makes sure the node is never asked for
        more than it will answer in one go.
        """
        out: list[dict[str, Any]] = []
        start = max(0, from_block)
        while start <= to_block:
            end = min(start + MAX_LOG_RANGE - 1, to_block)
            params: dict[str, Any] = {
                "fromBlock": hex(start),
                "toBlock": hex(end),
                "topics": topics,
            }
            if address:
                params["address"] = address
            out.extend(self.call("eth_getLogs", [params]) or [])
            start = end + 1
        return out
