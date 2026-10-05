"""Tiny HTTP listener on $PORT for OAuth callbacks (/xero-callback, /gmail-callback) and /healthz."""

from __future__ import annotations

import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)
_started = False


class _H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # never log query strings (codes)
        pass

    def _send(self, code: int, msg: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(msg.encode())

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/healthz"):
                return self._send(200, "ok")
            if u.path == "/xero-connect":
                from . import xero
                self.send_response(302)
                self.send_header("Location", xero.authorize_url())  # fresh state every time
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            if u.path == "/xero-callback":
                from . import xero
                ok = xero.handle_callback(q.get("code", ""), q.get("state", ""))
                return self._send(200 if ok else 400, "Xero connected (read-only). You can close this tab." if ok else "Xero connection failed.")
            if u.path == "/gmail-callback":
                from . import gmail
                ok = gmail.handle_callback(q.get("code", ""), q.get("state", ""))
                return self._send(200 if ok else 400, "Gmail connected (read-only). You can close this tab." if ok else "Gmail connection failed.")
        except Exception:
            logger.exception("callback failed")
            return self._send(500, "error")
        self._send(404, "not found")


def start() -> None:
    global _started
    port = os.environ.get("PORT")
    if _started or not port or os.environ.get("SOL_CALLBACK_SERVER", "1") == "0":
        return
    try:
        srv = HTTPServer(("0.0.0.0", int(port)), _H)
    except OSError:
        return  # another process already owns the port
    _started = True
    threading.Thread(target=srv.serve_forever, name="sol-callbacks", daemon=True).start()
