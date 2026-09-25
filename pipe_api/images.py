from __future__ import annotations

"""
Coin pictures, fetched by us instead of by the browser.

A coin's image lives wherever whoever launched it put it, and a good share of
those places will not serve a browser on someone else's page: ipfs.io answers
403, pinata's public gateway rate limits, twimg blocks hotlinks outright, and
some hosts send no CORS headers at all. Each failure shows up as the generated
mark, which reads as a broken terminal rather than as a picky gateway.

Fetching server side removes all of it at once. There is no CORS between two
servers, the gateway chain can be walked without the browser knowing, and the
answer is cached at the edge so the next reader pays nothing.

It is deliberately not an open proxy: https only, no private addresses, a size
cap, a short timeout, and the response is refused unless it really is an image.
"""

import ipaddress
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pipe.config import user_agent

MAX_BYTES = 6 * 1024 * 1024
TIMEOUT = 12

# The same rewrite the feed does, applied again here so a stored ipfs.io URL
# still resolves when it reaches the proxy.
GATEWAYS = (
    "https://pump.mypinata.cloud/ipfs/",
    "https://gateway.pinata.cloud/ipfs/",
    "https://ipfs.filebase.io/ipfs/",
)


def _private(host: str) -> bool:
    try:
        for info in socket.getaddrinfo(host, None):
            address = ipaddress.ip_address(info[4][0])
            if address.is_private or address.is_loopback or address.is_reserved or address.is_link_local:
                return True
    except (socket.gaierror, ValueError):
        return True
    return False


def candidates(url: str) -> list[str]:
    out = [url]
    cut = url.find("/ipfs/")
    if cut > -1:
        cid = url[cut + 6 :]
        for gateway in GATEWAYS:
            if gateway + cid not in out:
                out.append(gateway + cid)
    return out


def fetch(url: str) -> tuple[int, str, bytes]:
    """
    The image bytes, or a status saying why not. Every candidate gateway is
    tried before giving up, because the CID that one refuses another serves.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return 400, "text/plain", b"https only"
    if _private(parsed.hostname):
        return 400, "text/plain", b"not a public host"

    for candidate in candidates(url):
        request = Request(
            candidate,
            headers={"User-Agent": user_agent(), "Accept": "image/*,*/*;q=0.8"},
        )
        try:
            with urlopen(request, timeout=TIMEOUT) as response:
                kind = (response.headers.get("Content-Type") or "").split(";")[0].strip()
                if not kind.startswith("image/"):
                    continue
                body = response.read(MAX_BYTES + 1)
                if len(body) > MAX_BYTES:
                    continue
                return 200, kind, body
        except (HTTPError, URLError, TimeoutError, OSError):
            continue
    return 404, "text/plain", b"no gateway served this image"
