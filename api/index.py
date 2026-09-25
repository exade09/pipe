from __future__ import annotations

"""
Vercel's entry point. Serves the API and, for everything else, the built
frontend out of web/dist so one deployment carries both.
"""

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pipe_api.dispatch import handle_get, handle_post
from pipe_api.images import fetch as fetch_image

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "dist"


def holding() -> bool:
    """
    Whether the front door is the holding page instead of the terminal.

    It is a switch rather than a removal: SITE_MODE=soon puts SOON in front of
    every page, and unsetting it brings the terminal back with nothing to
    rebuild. The API keeps answering underneath either way, so the cron, the
    database and anything already pointed at a route carry on.
    """
    return (os.getenv("SITE_MODE") or "").strip().lower() == "soon"


def _send(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(body)


def _static(handler: BaseHTTPRequestHandler, path: str) -> bool:
    rel = path.lstrip("/") or "index.html"
    if holding():
        # Everything that is not the API resolves to the same page, so no
        # route of the terminal is reachable by typing it.
        rel = "soon.html"
    target = (WEB / rel).resolve()
    if not str(target).startswith(str(WEB.resolve())) or not target.is_file():
        target = WEB / "index.html"
    if not target.is_file():
        return False
    data = target.read_bytes()
    kind = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    handler.send_response(200)
    handler.send_header("Content-Type", kind)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header(
        "Cache-Control",
        "public, max-age=31536000, immutable" if "/assets/" in str(target).replace("\\", "/") else "no-cache",
    )
    handler.end_headers()
    handler.wfile.write(data)
    return True


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/image":
            # Images are bytes, not an envelope, and they are cached hard: a
            # coin's picture does not change, so the second reader should never
            # reach this function at all.
            target = (parse_qs(parsed.query).get("u") or [""])[0]
            status, kind, body = fetch_image(target) if target else (400, "text/plain", b"no url")
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header(
                "Cache-Control",
                "public, max-age=604800, immutable" if status == 200 else "public, max-age=60",
            )
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path.startswith("/api/"):
            # A route that raises must still answer. Without this the socket
            # simply closes and the browser reports "Failed to fetch", which
            # says nothing about what actually went wrong.
            try:
                routed = handle_get(parsed.path, parse_qs(parsed.query))
            except Exception as exc:
                _send(self, 502, {"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"})
                return
            if routed is None:
                _send(self, 404, {"ok": False, "data": None, "error": "Not found"})
            else:
                _send(self, routed[0], routed[1])
            return
        if not _static(self, parsed.path):
            _send(self, 404, {"ok": False, "data": None, "error": "Not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        want = (os.getenv("CRON_SECRET") or "").strip()
        got = (self.headers.get("Authorization") or "").replace("Bearer ", "").strip()
        body: dict = {}
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if 0 < length <= 2_000_000:
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8")) or {}
            except (ValueError, UnicodeDecodeError):
                _send(self, 400, {"ok": False, "data": None, "error": "Body was not JSON."})
                return
            if not isinstance(body, dict):
                body = {}
        try:
            forwarded = (self.headers.get("X-Forwarded-For") or "").split(",", 1)[0].strip()
            client_id = forwarded or (self.client_address[0] if self.client_address else "")
            routed = handle_post(parsed.path, bool(want) and got == want, body, client_id)
        except Exception as exc:
            _send(self, 502, {"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"})
            return
        if routed is None:
            _send(self, 404, {"ok": False, "data": None, "error": "Not found"})
        else:
            _send(self, routed[0], routed[1])

    def log_message(self, fmt: str, *args: object) -> None:
        return
