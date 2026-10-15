"""FinVerified Equity Room: cap table read, proposal list, and PENDING change proposals.

The read key comes from the environment and is never logged or returned.
Errors carry a status code and a fixed string or exception class name, never a body or URL.
Nothing here edits the cap table. propose only submits a pending change for approval.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from . import common

EQUITY_URL = "https://owner.finverified.ai/owner/api/state"
PROPOSALS_URL = "https://owner.finverified.ai/owner/api/proposals"
PROPOSAL_ACTIONS = ("add_holder", "add_issuance", "update_issuance", "cancel_issuance")


def _call(method: str, url: str, body: Any = None, extra: Dict[str, str] = None) -> Dict[str, Any]:
    key = os.environ.get("EQUITY_ROOM_READ_KEY", "")
    if not key:
        return {"success": False, "status": None, "error": "EQUITY_ROOM_READ_KEY not set"}
    headers = {"Authorization": "Bearer " + key, "Accept": "application/json", **(extra or {})}
    try:
        data = common.http_json(method, url, headers=headers, body=body, timeout=15)
    except common.HttpError as e:
        return {"success": False, "status": e.status, "error": "Equity Room request failed"}
    except Exception as e:  # timeout, URLError, JSON decode: class name only
        return {"success": False, "status": None, "error": type(e).__name__}
    if isinstance(data, dict):
        return {"success": True, **data}
    return {"success": True, "data": data}


def cap_table() -> Dict[str, Any]:
    return _call("GET", EQUITY_URL)


def list_proposals() -> Dict[str, Any]:
    return _call("GET", PROPOSALS_URL)


def propose(change: Any, payload: Any, reason: Any, doc_link: Any) -> Dict[str, Any]:
    if change not in PROPOSAL_ACTIONS:
        return {"success": False, "status": None, "error": "invalid change type"}
    if not isinstance(payload, dict) or not isinstance(reason, str) or not reason.strip():
        return {"success": False, "status": None, "error": "payload object and reason required"}
    if not isinstance(doc_link, str) or not doc_link.startswith("https://"):
        return {"success": False, "status": None, "error": "docLink must be https"}
    body = {"action": change, "payload": payload, "reason": reason, "docLink": doc_link}
    return _call("POST", PROPOSALS_URL, body=body, extra={"x-fv": "1", "Content-Type": "application/json"})
