"""Mercury: READ ONLY. GET requests only; the read token cannot approve or release payments."""

from __future__ import annotations

import os
from typing import Any, Dict

from . import common

BASE = "https://api.mercury.com/api/v1"


def _get(path: str, params: Dict[str, Any] = None) -> Any:
    from urllib.parse import urlencode
    q = ("?" + urlencode({k: v for k, v in (params or {}).items() if v is not None})) if params else ""
    return common.http_json("GET", BASE + path + q,
                            headers={"Authorization": "Bearer " + os.environ.get("MERCURY_READ_TOKEN", ""),
                                     "Accept": "application/json"})


def _mask(acct: Dict[str, Any]) -> Dict[str, Any]:
    keep = ("id", "name", "nickname", "kind", "status", "type", "currentBalance", "availableBalance")
    out = {k: acct.get(k) for k in keep if k in acct}
    num = str(acct.get("accountNumber", ""))
    if num:
        out["accountLast4"] = num[-4:]
    return out


def accounts() -> Dict[str, Any]:
    return {"accounts": [_mask(a) for a in (_get("/accounts").get("accounts") or [])]}


def transactions(account_id: str, start: str = None, end: str = None, limit: int = 200) -> Dict[str, Any]:
    r = _get(f"/account/{account_id}/transactions", {"start": start, "end": end, "limit": min(int(limit), 500)})
    keep = ("id", "amount", "status", "postedAt", "createdAt", "counterpartyName", "bankDescription", "kind", "note")
    return {"transactions": [{k: t.get(k) for k in keep if k in t} for t in (r.get("transactions") or [])]}
