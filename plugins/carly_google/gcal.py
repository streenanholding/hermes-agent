"""Read-only Google Calendar for CARLY_GOOGLE_ACCOUNT (calendar.readonly scope).

Lists events on the primary calendar. No create, update, delete or RSVP function,
and the OAuth scope could not do them anyway. Event text is untrusted.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from . import auth, common
from .gmail import UNTRUSTED

_API = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
_NY = ZoneInfo("America/New_York")


def _iso(value: Optional[str], default: datetime) -> str:
    if not value:
        return default.isoformat()
    v = value.strip()
    if len(v) == 10:  # YYYY-MM-DD
        v += "T00:00:00"
    dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_NY)  # Rick's time zone when no offset is given
    return dt.isoformat()


def events(start: Optional[str] = None, end: Optional[str] = None, max_results: int = 50) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    t_min = _iso(start, now)
    t_max = _iso(end, now + timedelta(days=7))
    if datetime.fromisoformat(t_max) <= datetime.fromisoformat(t_min):
        raise common.PolicyError("end must be after start")
    if datetime.fromisoformat(t_max) - datetime.fromisoformat(t_min) > timedelta(days=62):
        raise common.PolicyError("range too long: ask for at most about two months at a time")
    q = urlencode({"timeMin": t_min, "timeMax": t_max, "singleEvents": "true", "orderBy": "startTime",
                   "maxResults": max(1, min(int(max_results), 100))})
    data = common.http_json("GET", f"{_API}?{q}", headers=auth.headers())
    out: List[Dict[str, Any]] = []
    for e in data.get("items", []):
        if e.get("status") == "cancelled":
            continue
        out.append({
            "title": e.get("summary"),
            "start": (e.get("start") or {}).get("dateTime") or (e.get("start") or {}).get("date"),
            "end": (e.get("end") or {}).get("dateTime") or (e.get("end") or {}).get("date"),
            "location": e.get("location"),
            "meeting_link": e.get("hangoutLink"),
            "organizer": (e.get("organizer") or {}).get("email"),
            "attendees": [a.get("email") for a in (e.get("attendees") or [])][:25],
            "my_response": next((a.get("responseStatus") for a in (e.get("attendees") or []) if a.get("self")), None),
            "description": (e.get("description") or "")[:1500],
        })
    return {"events": out, "time_min": t_min, "time_max": t_max, "notice": UNTRUSTED}
