"""agent_kb plugin (FIN-1413): kb_search calls the service with the agent's token and stays read-only."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from plugins import agent_kb

SEEN = {}


class _H(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        SEEN["path"] = self.path
        SEEN["auth"] = self.headers.get("Authorization")
        SEEN["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if SEEN["auth"] != "Bearer good-token":
            self.send_response(401)
            self.end_headers()
            return
        payload = json.dumps({"results": [{"title": "Pricing v3", "text": "398 annual"}], "note": "cite"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):
        pass


@pytest.fixture()
def server(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("AGENT_KB_URL", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setenv("AGENT_KB_TOKEN", "good-token")
    yield
    srv.shutdown()


def test_search_sends_token_and_returns_results(server):
    out = json.loads(agent_kb.kb_search({"query": "annual price", "k": 3}))
    assert out["success"] and out["results"][0]["title"] == "Pricing v3"
    assert SEEN["path"] == "/v1/search" and SEEN["auth"] == "Bearer good-token"
    assert SEEN["body"] == {"query": "annual price", "k": 3}


def test_audience_cannot_be_passed(server):
    agent_kb.kb_search({"query": "cap table", "audience": "sol"})
    assert "audience" not in SEEN["body"]


def test_bad_token_reports_error(server, monkeypatch):
    monkeypatch.setenv("AGENT_KB_TOKEN", "wrong")
    out = json.loads(agent_kb.kb_search({"query": "annual price"}))
    assert out == {"success": False, "error": "knowledge library returned HTTP 401"}


def test_unreachable_reports_error(monkeypatch):
    monkeypatch.setenv("AGENT_KB_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("AGENT_KB_TOKEN", "t")
    out = json.loads(agent_kb.kb_search({"query": "annual price"}))
    assert not out["success"] and "unreachable" in out["error"]


def test_requirements_gate(monkeypatch):
    monkeypatch.delenv("AGENT_KB_URL", raising=False)
    assert agent_kb.check_requirements() is False


def test_registers_single_read_only_tool():
    calls = []

    class Ctx:
        def register_tool(self, **kw):
            calls.append(kw)

    agent_kb.register(Ctx())
    assert [c["name"] for c in calls] == ["kb_search"] and calls[0]["toolset"] == "agent_kb"
    assert set(calls[0]["schema"]["parameters"]["properties"]) == {"query", "k"}
