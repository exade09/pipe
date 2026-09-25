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

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "dist"


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
