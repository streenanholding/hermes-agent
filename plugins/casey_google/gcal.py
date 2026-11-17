"""Casey's OWN calendar (calendar.events): create_event() only, always on her primary calendar,
with a Google Meet link. Invites are emails, so attendees follow the mailbox allowlist rules.
Window: Monday-Friday, 8:00 AM-8:00 PM Eastern (clinics and partners span time zones)."""

from __future__ import annotations

import uuid
from datetime import datetime, time as dtime, timedelta
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from . import approvals, auth, common, mailbox

_API = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
_NY = ZoneInfo("America/New_York")
BUSINESS_WEEKDAYS = (0, 1, 2, 3, 4)
BUSINESS_OPEN, BUSINESS_CLOSE = dtime(8, 0), dtime(20, 0)


def _dt(value: Any, field: str) -> datetime:
    if not value:
        raise common.PolicyError(f"missing {field}")
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        raise common.PolicyError(f"{field} is not an ISO date-time: {value}")
    return (dt.replace(tzinfo=_NY) if dt.tzinfo is None else dt).astimezone(_NY)


def check_window(start: Any, end: Any) -> tuple:
    s, e = _dt(start, "start"), _dt(end, "end")
    if e <= s:
        raise common.PolicyError("end must be after start")
    if e - s > timedelta(hours=2):
        raise common.PolicyError("event too long (max 2 hours)")
    if s.date() != e.date():
        raise common.PolicyError("events must start and end on the same day (ET)")
    if s.weekday() not in BUSINESS_WEEKDAYS:
        raise common.PolicyError("events are Monday to Friday only (ET)")
    if s.time() < BUSINESS_OPEN or e.time() > BUSINESS_CLOSE:
        raise common.PolicyError("events must fall between 8:00 AM and 8:00 PM ET")
    return s, e


def event_payload(args: Dict[str, Any]) -> Dict[str, Any]:
    title = str(args.get("title") or "").strip()
    if not title:
        raise common.PolicyError("missing title")
    s, e = check_window(args.get("start"), args.get("end"))
    attendees = mailbox.normalize_recipients(args.get("attendees"), "attendees")
    if not attendees:
        raise common.PolicyError("missing attendees")
    return {"title": title, "start": s.isoformat(), "end": e.isoformat(), "attendees": attendees,
            "description": str(args.get("description") or "")[:4000]}


def propose_event(args: Dict[str, Any]) -> Dict[str, Any]:
    payload = event_payload(args)
    item = approvals.propose("event", payload)
    return {"approval_token": item["token"], "event": payload,
            "attendees_needing_approval": mailbox.off_allowlist(payload["attendees"]),
            "next": "Post the full event in Slack. After Rick or Kirk says yes, call confirm with this token, then "
                    "create_event with approval_token and the same fields."}


def create_event(args: Dict[str, Any], approval_token: Optional[str] = None) -> Dict[str, Any]:
    p = event_payload(args)
    mailbox._check_suppressed(p["attendees"])
    outside = mailbox.off_allowlist(p["attendees"])
    if outside:
        if not approval_token:
            raise common.PolicyError("attendee(s) need approval (" + ", ".join(outside) + "): use propose_event, get a "
                                     "yes, confirm, then create_event with approval_token")
        approvals.consume(approval_token, "event", p)
    body = {"summary": p["title"], "description": p["description"],
            "start": {"dateTime": p["start"], "timeZone": "America/New_York"},
            "end": {"dateTime": p["end"], "timeZone": "America/New_York"},
            "attendees": [{"email": a} for a in p["attendees"]],
            "conferenceData": {"createRequest": {"requestId": uuid.uuid4().hex,
                                                 "conferenceSolutionKey": {"type": "hangoutsMeet"}}}}
    res = common.http_json("POST", f"{_API}?conferenceDataVersion=1&sendUpdates=all", headers=auth.OWN.headers(), body=body)
    return {"created": True, "calendar": common.own_account(), "event_id": (res or {}).get("id"),
            "link": (res or {}).get("htmlLink"), "meet_link": (res or {}).get("hangoutLink"), "event": p}
