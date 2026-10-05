"""Approval ledger. Approvals are valid only from the approver's Slack user ID,
tied to an item ID, and void if any value in the item changes afterwards.

Identity comes from the gateway session (HERMES_SESSION_USER_ID), never from
model-supplied arguments.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any, Dict, Optional, Tuple

from .common import load_state, save_state

_FILE = "approvals.json"
# kinds that Nancy (not Rick) countersigns
NANCY_KINDS = {"countersign", "equity"}


def rick_id() -> str:
    return os.environ.get("SOL_RICK_SLACK_ID", "").strip()


def nancy_id() -> str:
    return os.environ.get("SOL_NANCY_SLACK_ID", "").strip()


def payload_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def allowed_approver(kind: str, user_id: str) -> bool:
    if not user_id:
        return False
    allowed = {rick_id()}
    if kind in NANCY_KINDS:
        allowed.add(nancy_id())
    allowed.discard("")
    return user_id in allowed


def propose(item_id: str, kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create or amend an item. Amending clears any prior approval."""
    ledger = load_state(_FILE, {})
    h = payload_hash(payload)
    cur = ledger.get(item_id)
    if cur and cur.get("hash") == h and cur.get("kind") == kind:
        return cur
    ledger[item_id] = {"kind": kind, "payload": payload, "hash": h, "approved_by": None,
                       "approved_hash": None, "approved_at": None, "created_at": time.time()}
    save_state(_FILE, ledger)
    return ledger[item_id]


def approve(item_id: str, user_id: str) -> Tuple[bool, str]:
    ledger = load_state(_FILE, {})
    item = ledger.get(item_id)
    if not item:
        return False, "unknown item"
    if not allowed_approver(item["kind"], user_id):
        return False, "ignored: approval must come from the authorized approver's Slack ID"
    item["approved_by"], item["approved_hash"], item["approved_at"] = user_id, item["hash"], time.time()
    save_state(_FILE, ledger)
    return True, "approved"


def is_approved(item_id: str, current_payload: Dict[str, Any]) -> bool:
    """True only if approved by an authorized ID AND the payload is unchanged since."""
    item = load_state(_FILE, {}).get(item_id)
    if not item or not item.get("approved_by"):
        return False
    if not allowed_approver(item["kind"], item["approved_by"]):
        return False
    return item["approved_hash"] == payload_hash(current_payload) == item["hash"]


_RAISE = re.compile(r"^\s*RAISE\s+(50|100)\s*$", re.I)


def parse_raise(text: str, user_id: str) -> Optional[int]:
    """RAISE 50 / RAISE 100 counts only from Rick's Slack ID."""
    m = _RAISE.match(text or "")
    if m and user_id and user_id == rick_id():
        return int(m.group(1))
    return None
