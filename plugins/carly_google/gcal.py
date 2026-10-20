"""Google Calendar.

* Rick's calendar (CARLY_GOOGLE_ACCOUNT, calendar.readonly): events() and free_busy() only.
  No create, update, delete or RSVP function, and the OAuth scope could not do them anyway.
* Carly's OWN calendar (CARLY_OWN_ACCOUNT, calendar.events): create_event() only. It always
  writes to the own account's primary calendar and never to Rick's; Rick's calendar changes only
  when Rick accepts the invite. Scheduling rules are enforced in check_window().
Event text is untrusted.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from . import approvals, auth, common, mailbox
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


# --- Free/busy on Rick's calendar (read) ---------------------------------------------------------
def _range(start: Optional[str], end: Optional[str]) -> tuple:
    now = datetime.now(timezone.utc)
    t_min = _iso(start, now)
    t_max = _iso(end, now + timedelta(days=7))
    if datetime.fromisoformat(t_max) <= datetime.fromisoformat(t_min):
        raise common.PolicyError("end must be after start")
    if datetime.fromisoformat(t_max) - datetime.fromisoformat(t_min) > timedelta(days=62):
        raise common.PolicyError("range too long: ask for at most about two months at a time")
    return t_min, t_max


def free_busy(start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, Any]:
    """Busy blocks (no titles, no attendees) on Rick's primary calendar. Uses Rick's read-only token."""
    t_min, t_max = _range(start, end)
    data = common.http_json("POST", "https://www.googleapis.com/calendar/v3/freeBusy", headers=auth.headers(),
                            body={"timeMin": t_min, "timeMax": t_max, "timeZone": "America/New_York",
                                  "items": [{"id": "primary"}]})
    cal = (data.get("calendars") or {}).get("primary") or {}
    if cal.get("errors"):
        raise common.PolicyError("free/busy unavailable for Rick's calendar: " + str(cal["errors"])[:200])
    return {"busy": [{"start": b.get("start"), "end": b.get("end")} for b in cal.get("busy", [])],
            "time_min": t_min, "time_max": t_max, "time_zone": "America/New_York"}


# --- Scheduling rules ---------------------------------------------------------------------------
BUSINESS_WEEKDAYS = (1, 2, 3)  # Tuesday, Wednesday, Thursday (Monday = 0)
BUSINESS_OPEN, BUSINESS_CLOSE = dtime(10, 0), dtime(14, 0)


def _truthy(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def _dt(value: Any, field: str) -> datetime:
    if not value:
        raise common.PolicyError(f"missing {field}")
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        raise common.PolicyError(f"{field} is not an ISO date-time: {value}")
    return (dt.replace(tzinfo=_NY) if dt.tzinfo is None else dt).astimezone(_NY)  # naive = Rick's time (ET)


def check_window(start: Any, end: Any, category: Any = "business", critical: Any = False) -> tuple:
    """Return (start, end) in America/New_York or raise PolicyError.

    Business meetings: Tue/Wed/Thu, starting no earlier than 10:00 and ending no later than 14:00 ET,
    same day, unless critical is exactly true. Only category 'personal' is exempt from the window;
    any other or missing category is treated as business (fail closed).
    """
    s, e = _dt(start, "start"), _dt(end, "end")
    if e <= s:
        raise common.PolicyError("end must be after start")
    if e - s > timedelta(hours=24):
        raise common.PolicyError("event too long (max 24 hours)")
    if str(category or "business").strip().lower() == "personal" or _truthy(critical):
        return s, e
    if s.date() != e.date():
        raise common.PolicyError("business meetings must start and end on the same day (ET)")
    if s.weekday() not in BUSINESS_WEEKDAYS:
        raise common.PolicyError("business meetings are Tuesday, Wednesday or Thursday only (ET); "
                                 "pass critical=true only if Rick said this meeting is critical")
    if s.time() < BUSINESS_OPEN or e.time() > BUSINESS_CLOSE:
        raise common.PolicyError("business meetings must fall between 10:00 AM and 2:00 PM ET; "
                                 "pass critical=true only if Rick said this meeting is critical")
    return s, e


def event_payload(args: Dict[str, Any]) -> Dict[str, Any]:
    """Validate everything about a new event and return the canonical payload (also what Rick approves)."""
    title = str(args.get("title") or "").strip()
    if not title:
        raise common.PolicyError("missing title")
    category = "personal" if str(args.get("category") or "").strip().lower() == "personal" else "business"
    critical = _truthy(args.get("critical"))
    s, e = check_window(args.get("start"), args.get("end"), category, critical)
    attendees = mailbox.normalize_recipients(args.get("attendees"), "attendees")
    return {"title": title, "start": s.isoformat(), "end": e.isoformat(), "attendees": attendees,
            "description": str(args.get("description") or "")[:4000], "category": category, "critical": critical}


def propose_event(args: Dict[str, Any]) -> Dict[str, Any]:
    payload = event_payload(args)
    item = approvals.propose("event", payload)
    return {"approval_token": item["token"], "event": payload,
            "attendees_needing_approval": mailbox.off_allowlist(payload["attendees"]),
            "next": "Show Rick the full event. Only after he says yes, call confirm with this token, then create_event "
                    "with approval_token and the same fields."}


def create_event(args: Dict[str, Any], approval_token: Optional[str] = None) -> Dict[str, Any]:
    """Create the event on Carly's OWN calendar with a Google Meet link. Invites go out to attendees.

    An invite is an email, so attendees outside CARLY_SEND_ALLOWLIST need the same single-use
    approval token as an outside email.
    """
    p = event_payload(args)
    outside = mailbox.off_allowlist(p["attendees"])
    if outside:
        if not approval_token:
            raise common.PolicyError("attendee(s) not on the allowlist (" + ", ".join(outside) + "): use propose_event, "
                                     "get Rick's yes, confirm, then create_event with approval_token")
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
