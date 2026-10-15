"""FinVerified Equity Room cap table, READ ONLY.

GET only. The read key comes from the environment and is never logged or returned.
Errors carry a status code and a fixed string or exception class name, never a body or URL.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from . import common

EQUITY_URL = "https://owner.finverified.ai/owner/api/state"


def cap_table() -> Dict[str, Any]:
    key = os.environ.get("EQUITY_ROOM_READ_KEY", "")
    if not key:
        return {"success": False, "status": None, "error": "EQUITY_ROOM_READ_KEY not set"}
    try:
        data = common.http_json("GET", EQUITY_URL,
                                headers={"Authorization": "Bearer " + key, "Accept": "application/json"},
                                timeout=15)
    except common.HttpError as e:
        return {"success": False, "status": e.status, "error": "Equity Room request failed"}
    except Exception as e:  # timeout, URLError, JSON decode: class name only
        return {"success": False, "status": None, "error": type(e).__name__}
    if isinstance(data, dict):
        return {"success": True, **data}
    return {"success": True, "data": data}
