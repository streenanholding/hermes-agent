"""Who Casey may email without asking: the team, plus anyone who exists in Attio as a Person with a
FinVerified role set by the platform sync (partners, clinic contacts, integration contacts).

A person Attio merely ingested from an email thread has no role and does NOT qualify. Lookups use
the same ATTIO_API_KEY as the casey_attio plugin and are cached for ten minutes. Attio being down
fails closed: the address is treated as outside the allowlist, so it needs an approval token.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from . import common

_ATTIO = "https://api.attio.com/v2"
_CACHE: Dict[str, tuple] = {}
_TTL = 600
ALLOWED_ROLES = {
    "pathway partner", "partner org admin", "channel lead", "clinic owner", "office manager", "clinic staff",
    "lender contact", "processor contact", "benefits contact", "marketplace contact", "pms vendor contact",
}


def _token() -> str:
    return os.environ.get("ATTIO_API_KEY", "").strip()


def _role_of(record: Dict[str, Any]) -> str:
    vals = (record.get("values") or {}).get("fv_role") or []
    if not vals:
        return ""
    opt = vals[0].get("option") or {}
    return str(opt.get("title") or "").strip().lower()


def lookup(email: str) -> Optional[Dict[str, Any]]:
    """Return {record_id, name, role} for a Person with this email, or None. Never raises."""
    email = (email or "").strip().lower()
    if not email or not _token():
        return None
    hit = _CACHE.get(email)
    if hit and hit[0] > time.time():
        return hit[1]
    result = None
    try:
        data = common.http_json(
            "POST", f"{_ATTIO}/objects/people/records/query",
            headers={"Authorization": "Bearer " + _token()},
            body={"filter": {"email_addresses": {"email_address": {"$eq": email}}}, "limit": 1}, timeout=8)
        recs = data.get("data") or []
        if recs:
            rec = recs[0]
            name_vals = (rec.get("values") or {}).get("name") or []
            result = {"record_id": ((rec.get("id") or {}).get("record_id")),
                      "name": (name_vals[0].get("full_name") if name_vals else "") or "",
                      "role": _role_of(rec)}
    except Exception:
        result = None  # fail closed
    _CACHE[email] = (time.time() + _TTL, result)
    return result


def known_contact(email: str) -> bool:
    person = lookup(email)
    return bool(person and person.get("role") in ALLOWED_ROLES)


def clear_cache() -> None:
    _CACHE.clear()
