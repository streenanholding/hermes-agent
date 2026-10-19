"""Calendar: Carly's own calendar ("primary") and Rick's calendar ("rick"), the latter
only because Rick shared it with CARLY_EMAIL. Any other calendar id is refused.
No delete function. Invitations are not emailed unless ``carly.allow_send`` is true.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode

from . import auth, common

_API = "https://www.googleapis.com/calendar/v3"
_FIELDS = "id,summary,start,end,location,description,attendees(email,responseStatus),htmlLink,status"


def calendar_id(name: str) -> str:
    n = (name or "primary").strip().lower()
    if n == "primary":
        return "primary"
    if n == "rick":
        return common.env_required("CARLY_RICK_CALENDAR_ID")
    raise common.PolicyError("Only the 'primary' (Carly) and 'rick' calendars are available")


def _tz() -> str:
    return str(common.carly_config().get("timezone") or os.environ.get("TZ") or "America/New_York")


def list_events(calendar: str, time_min: str, time_max: str, max_results: int = 50) -> Dict[str, Any]:
    q = urlencode({"timeMin": time_min, "timeMax": time_max, "singleEvents": "true", "orderBy": "startTime",
                   "maxResults": min(int(max_results), 100), "fields": f"items({_FIELDS})"})
    r = common.http_json("GET", f"{_API}/calendars/{quote(calendar_id(calendar), safe='')}/events?{q}", headers=auth.headers())
    return {"events": r.get("items", [])}


def freebusy(time_min: str, time_max: str, calendars: Optional[List[str]] = None) -> Dict[str, Any]:
    ids = [calendar_id(c) for c in (calendars or ["primary", "rick"])]
    r = common.http_json("POST", f"{_API}/freeBusy", headers=auth.headers(),
                         body={"timeMin": time_min, "timeMax": time_max, "items": [{"id": i} for i in ids]})
    return {"busy": {k: v.get("busy", []) for k, v in r.get("calendars", {}).items()}}


def _send_updates() -> str:
    return "all" if common.carly_config().get("allow_send") else "none"


def create_event(calendar: str, summary: str, start: str, end: str, attendees: Optional[List[str]] = None,
                 description: Optional[str] = None, location: Optional[str] = None) -> Dict[str, Any]:
    ev: Dict[str, Any] = {"summary": summary, "start": {"dateTime": start, "timeZone": _tz()},
                          "end": {"dateTime": end, "timeZone": _tz()}}
    if attendees:
        ev["attendees"] = [{"email": a} for a in attendees]
    if description:
        ev["description"] = description
    if location:
        ev["location"] = location
    r = common.http_json("POST", f"{_API}/calendars/{quote(calendar_id(calendar), safe='')}/events?sendUpdates={_send_updates()}",
                         headers=auth.headers(), body=ev)
    return {"event_id": r.get("id"), "link": r.get("htmlLink"), "invitations_emailed": _send_updates() == "all"}


def update_event(calendar: str, event_id: str, summary: Optional[str] = None, start: Optional[str] = None,
                 end: Optional[str] = None, description: Optional[str] = None, location: Optional[str] = None) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}
    if summary is not None:
        patch["summary"] = summary
    if start is not None:
        patch["start"] = {"dateTime": start, "timeZone": _tz()}
    if end is not None:
        patch["end"] = {"dateTime": end, "timeZone": _tz()}
    if description is not None:
        patch["description"] = description
    if location is not None:
        patch["location"] = location
    if not patch:
        raise common.PolicyError("Nothing to update")
    r = common.http_json("PATCH", f"{_API}/calendars/{quote(calendar_id(calendar), safe='')}/events/{quote(event_id, safe='')}?sendUpdates={_send_updates()}",
                         headers=auth.headers(), body=patch)
    return {"event_id": r.get("id"), "link": r.get("htmlLink")}
