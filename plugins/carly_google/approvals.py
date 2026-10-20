"""Single-use approval tokens for anything Carly does that reaches an outside person.

Flow (same idea as plugins/sol_finance/approvals.py, plus a one-time token):
  1. propose(kind, payload) stores the exact item and returns a token. Carly shows Rick the full
     item. Nothing can be sent or created with an unconfirmed token.
  2. confirm(token, user_id) records Rick's yes. Identity comes from the gateway session
     (HERMES_SESSION_USER_ID), never from model arguments, and must be one of CARLY_RICK_USER_IDS
     (comma-separated Slack and/or Telegram user IDs). Unset = nobody can confirm (fail closed).
  3. consume(token, kind, payload) is checked by the action itself: the token must be confirmed,
     unused, unexpired, for the same kind, and the payload must be byte-for-byte what Rick saw.
     It is marked used before the action runs, so it can never be replayed.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from typing import Any, Dict, Set, Tuple

from . import common

_FILE = "approvals.json"
TTL_SECONDS = 24 * 3600
_lock = threading.Lock()


def rick_ids() -> Set[str]:
    return {x.strip() for x in os.environ.get("CARLY_RICK_USER_IDS", "").split(",") if x.strip()}


def payload_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def propose(kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    token = secrets.token_urlsafe(16)
    now = time.time()
    with _lock:
        ledger = {t: i for t, i in common.load_state(_FILE, {}).items() if now - i.get("created_at", 0) < TTL_SECONDS}
        ledger[token] = {"kind": kind, "payload": payload, "hash": payload_hash(payload), "created_at": now,
                         "confirmed_by": None, "used": False}
        common.save_state(_FILE, ledger)
    return {"token": token, "kind": kind, "payload": payload, "expires_in_hours": TTL_SECONDS // 3600}


def confirm(token: str, user_id: str) -> Tuple[bool, str]:
    with _lock:
        ledger = common.load_state(_FILE, {})
        item = ledger.get(token or "")
        if not item:
            return False, "unknown or expired token"
        if not user_id or user_id not in rick_ids():
            return False, "ignored: only Rick's own chat can confirm"
        if item["used"]:
            return False, "token already used"
        if time.time() - item["created_at"] > TTL_SECONDS:
            return False, "token expired; propose again"
        item["confirmed_by"] = user_id
        common.save_state(_FILE, ledger)
    return True, "confirmed (valid once, for exactly this item)"


def consume(token: str, kind: str, payload: Dict[str, Any]) -> None:
    """Raise PolicyError unless the token is confirmed, unused, fresh and matches this exact payload."""
    with _lock:
        ledger = common.load_state(_FILE, {})
        item = ledger.get(token or "")
        if not item:
            raise common.PolicyError("approval token unknown or expired: propose first and get Rick's yes")
        if item["used"]:
            raise common.PolicyError("approval token already used; each yes covers one item only")
        if time.time() - item["created_at"] > TTL_SECONDS:
            raise common.PolicyError("approval token expired; propose again")
        if not item.get("confirmed_by") or item["confirmed_by"] not in rick_ids():
            raise common.PolicyError("Rick has not confirmed this item yet; show him the full draft and wait for his yes")
        if item["kind"] != kind or item["hash"] != payload_hash(payload):
            raise common.PolicyError("item changed after Rick approved it; propose again")
        item["used"] = True
        common.save_state(_FILE, ledger)
