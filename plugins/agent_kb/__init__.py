"""agent_kb plugin: one read-only tool, kb_search, backed by the agent-kb Railway service (FIN-1413).

The agent's identity (and so which documents it may see) is decided by the
server from AGENT_KB_TOKEN. The tool has no write, edit or delete action.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict

_REQUIRED_ENV = ("AGENT_KB_URL", "AGENT_KB_TOKEN")
_TIMEOUT_S = 15

SCHEMA: Dict[str, Any] = {
    "name": "kb_search",
    "description": (
        "Search FinVerified's approved company knowledge library (pricing, rulings, brand rules, partner terms, "
        "contracts index, vendors, runbooks). Use it BEFORE stating any FinVerified business fact. "
        "Cite the returned title (and link if present) when you use a result. If nothing comes back, say you "
        "have no approved source instead of guessing."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Plain-language question or keywords."},
            "k": {"type": "integer", "minimum": 1, "maximum": 10, "description": "How many passages (default 5)."},
        },
        "required": ["query"],
    },
}


def check_requirements() -> bool:
    return all(os.environ.get(k) for k in _REQUIRED_ENV)


def kb_search(args: Dict[str, Any], **_kw) -> str:
    query = str(args.get("query") or "").strip()
    if len(query) < 2:
        return json.dumps({"success": False, "error": "query is required"})
    try:
        k = max(1, min(10, int(args.get("k") or 5)))
    except (TypeError, ValueError):
        k = 5
    req = urllib.request.Request(
        os.environ["AGENT_KB_URL"].rstrip("/") + "/v1/search",
        data=json.dumps({"query": query[:1000], "k": k}).encode(),
        method="POST",
        headers={"Authorization": "Bearer " + os.environ["AGENT_KB_TOKEN"], "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.dumps({"success": False, "error": f"knowledge library returned HTTP {e.code}"})
    except Exception as e:  # network/timeout: report plainly, never guess
        return json.dumps({"success": False, "error": f"knowledge library unreachable: {type(e).__name__}"})
    return json.dumps({"success": True, "results": data.get("results", []), "note": data.get("note", "")})


def register(ctx) -> None:
    ctx.register_tool(name="kb_search", toolset="agent_kb", schema=SCHEMA, handler=kb_search, emoji="📚",
                      check_fn=check_requirements, requires_env=list(_REQUIRED_ENV))
