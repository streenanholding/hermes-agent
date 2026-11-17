"""Casey's OWN mailbox (casey@finverified.ai): draft, send, reply. The rules live here, in code.

* From is always CASEY_OWN_ACCOUNT. No from argument, no attachments, no BCC, no forwarding.
* Who she may write to without asking:
    - the team (CASEY_SEND_ALLOWLIST; default rick@, ncoy@, sol@, seraphine@, carly@finverified.ai)
    - anyone who exists in Attio as a Person with a FinVerified role (contacts.known_contact)
    - the sender of an email she is replying to (they wrote to us first)
  Anyone else needs a single-use approval token: propose -> yes from Rick/Kirk/Nancy -> send.
* Supervised mode: while CASEY_SUPERVISED_UNTIL (YYYY-MM-DD) is in the future, Attio contacts are
  treated like outsiders too, so every external email goes through propose -> confirm first.
* Every email gets the CAN-SPAM footer (company address + how to stop). Addresses on the
  suppression list (unsubscribed) are refused.
* Proactive email (proactive=true): at most one per recipient per 72 hours, never between
  8 PM and 8 AM Eastern. Replies are exempt.
"""

from __future__ import annotations

import base64
import os
import re
import time
from datetime import date, datetime
from email.message import EmailMessage
from email.utils import getaddresses
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from . import approvals, auth, common, contacts, gmail

DEFAULT_ALLOWLIST = "rick@finverified.ai,ncoy@finverified.ai,sol@finverified.ai,seraphine@finverified.ai,carly@finverified.ai"
DEFAULT_FOOTER = ("--\nCasey Rivera · Partner & Customer Success · FinVerified, Inc.\n"
                  "11718 SE Federal Hwy, Suite 202, Hobe Sound, FL 33455\n"
                  "To stop receiving emails from me, reply with the word \"unsubscribe\".")
_API = "https://gmail.googleapis.com/gmail/v1/users/me"
_ADDR = re.compile(r"^[^@\s<>,;\"']+@[^@\s<>,;\"']+\.[^@\s<>,;\"']+$")
_NY = ZoneInfo("America/New_York")
MAX_RECIPIENTS = 20
PROACTIVE_GAP_SECONDS = 72 * 3600
QUIET_FROM, QUIET_TO = 20, 8  # 8 PM .. 8 AM ET
_OUTREACH = "outreach.json"
_SUPPRESSED = "suppressed.json"


def allowlist() -> List[str]:
    raw = os.environ.get("CASEY_SEND_ALLOWLIST")
    raw = DEFAULT_ALLOWLIST if raw is None else raw
    return [a.strip().lower() for a in raw.split(",") if a.strip()]


def footer() -> str:
    return os.environ.get("CASEY_EMAIL_FOOTER") or DEFAULT_FOOTER


def supervised() -> bool:
    raw = os.environ.get("CASEY_SUPERVISED_UNTIL", "").strip()
    if not raw:
        return False
    try:
        return date.today() < date.fromisoformat(raw)
    except ValueError:
        return True  # unparsable = stay supervised (fail closed)


def normalize_recipients(value: Any, field: str = "to") -> List[str]:
    """Accept a string ('a@x.com, b@y.com') or a list; return unique lowercase addresses or raise."""
    if value in (None, "", []):
        return []
    parts = [value] if isinstance(value, str) else list(value)
    found = getaddresses([str(p) for p in parts])
    out: List[str] = []
    for _name, addr in found:
        addr = addr.strip().lower()
        if not _ADDR.match(addr):
            raise common.PolicyError(f"invalid email address in {field}: {addr or '(blank)'}")
        if addr not in out:
            out.append(addr)
    if len(out) > MAX_RECIPIENTS:
        raise common.PolicyError(f"too many recipients (max {MAX_RECIPIENTS})")
    return out


# --- Suppression (unsubscribe) -------------------------------------------------------------------
def suppressed() -> List[str]:
    return [a.lower() for a in common.load_state(_SUPPRESSED, [])]


def suppress(email: str, reason: str = "asked to stop") -> Dict[str, Any]:
    addr = normalize_recipients(email, "email")[0]
    current = suppressed()
    if addr not in current:
        current.append(addr)
        common.save_state(_SUPPRESSED, sorted(current))
    log = common.load_state("suppression_log.json", [])
    log.append({"email": addr, "reason": reason[:200], "at": datetime.now(_NY).isoformat()})
    common.save_state("suppression_log.json", log[-500:])
    return {"suppressed": True, "email": addr}


# --- Who may be emailed ---------------------------------------------------------------------------
def off_allowlist(addresses: List[str], reply_to_sender: Optional[str] = None) -> List[str]:
    """Addresses that need an approval token."""
    allowed = set(allowlist())
    out = []
    for a in addresses:
        if a in allowed or (reply_to_sender and a == reply_to_sender):
            continue
        if not supervised() and contacts.known_contact(a):
            continue
        out.append(a)
    return out


def _check_suppressed(addresses: List[str]) -> None:
    bad = [a for a in addresses if a in set(suppressed())]
    if bad:
        raise common.PolicyError("recipient asked us to stop emailing (" + ", ".join(bad) + "); do not contact them")


# --- Proactive limits --------------------------------------------------------------------------------
def _truthy(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def check_proactive(addresses: List[str], now: Optional[datetime] = None) -> None:
    now = now or datetime.now(_NY)
    if now.hour >= QUIET_FROM or now.hour < QUIET_TO:
        raise common.PolicyError("quiet hours: proactive email goes out between 8 AM and 8 PM Eastern only")
    sent = common.load_state(_OUTREACH, {})
    recent = [a for a in addresses if time.time() - float(sent.get(a, 0)) < PROACTIVE_GAP_SECONDS]
    if recent:
        raise common.PolicyError("already emailed proactively in the last 72 hours: " + ", ".join(recent))


def _record_proactive(addresses: List[str]) -> None:
    sent = common.load_state(_OUTREACH, {})
    cutoff = time.time() - 30 * 86400
    sent = {a: t for a, t in sent.items() if float(t) > cutoff}
    for a in addresses:
        sent[a] = time.time()
    common.save_state(_OUTREACH, sent)


# --- Drafts ---------------------------------------------------------------------------------------------
def build_draft(args: Dict[str, Any]) -> Dict[str, Any]:
    to = normalize_recipients(args.get("to"), "to")
    cc = [a for a in normalize_recipients(args.get("cc"), "cc") if a not in to]
    if not to:
        raise common.PolicyError("missing recipient (to)")
    subject = str(args.get("subject") or "").strip()
    body = str(args.get("body") or "")
    if not subject or "\n" in subject or "\r" in subject:
        raise common.PolicyError("subject must be a single non-empty line")
    if re.match(r"^\s*(fwd?|forward)\s*:", subject, re.I):
        raise common.PolicyError("forwarding is not allowed")
    if not body.strip():
        raise common.PolicyError("body is empty")
    if len(body) > 20000:
        raise common.PolicyError("body too long (max 20000 characters)")
    draft = {"to": to, "cc": cc, "subject": subject, "body": body, "proactive": _truthy(args.get("proactive"))}
    if args.get("in_reply_to"):
        draft["in_reply_to"] = str(args["in_reply_to"])
    return draft


def _raw(draft: Dict[str, Any], reply: Optional[Dict[str, Any]] = None) -> str:
    msg = EmailMessage()
    msg["From"] = common.own_account()  # always her own address; never an argument
    msg["To"] = ", ".join(draft["to"])
    if draft["cc"]:
        msg["Cc"] = ", ".join(draft["cc"])
    msg["Subject"] = draft["subject"]
    if reply and reply.get("message_id_header"):
        msg["In-Reply-To"] = reply["message_id_header"]
        msg["References"] = (reply.get("references", "") + " " + reply["message_id_header"]).strip()
    msg.set_content(draft["body"].rstrip() + "\n\n" + footer() + "\n")
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def _recipients(draft: Dict[str, Any]) -> List[str]:
    return draft["to"] + draft["cc"]


def propose(args: Dict[str, Any]) -> Dict[str, Any]:
    draft = build_draft(args)
    _check_suppressed(_recipients(draft))
    outside = off_allowlist(_recipients(draft))
    item = approvals.propose("email", draft)
    return {"approval_token": item["token"], "from": common.own_account(), "draft": draft,
            "recipients_needing_approval": outside, "supervised_mode": supervised(),
            "expires_in_hours": item["expires_in_hours"],
            "next": "Post the full draft (to, cc, subject, body) in Slack. Only after Rick, Kirk or Nancy says yes, "
                    "call confirm with this token, then send with approval_token. If they edit it, propose again."}


def create_draft(args: Dict[str, Any]) -> Dict[str, Any]:
    draft = build_draft(args)
    res = common.http_json("POST", f"{_API}/drafts", headers=auth.OWN.headers(), body={"message": {"raw": _raw(draft)}})
    return {"drafted": True, "draft_id": (res or {}).get("id"), "from": common.own_account(), "draft": draft,
            "needs_approval_to_send": off_allowlist(_recipients(draft))}


def send(args: Dict[str, Any], approval_token: Optional[str] = None) -> Dict[str, Any]:
    draft = build_draft(args)
    rcpts = _recipients(draft)
    _check_suppressed(rcpts)
    outside = off_allowlist(rcpts)
    if outside:
        if not approval_token:
            raise common.PolicyError("recipient(s) need approval (" + ", ".join(outside) + "): use propose, get a yes "
                                     "from Rick or Kirk, confirm, then send with approval_token")
        approvals.consume(approval_token, "email", draft)  # single use; marks the token used
    if draft["proactive"]:
        check_proactive(rcpts)
    res = common.http_json("POST", f"{_API}/messages/send", headers=auth.OWN.headers(), body={"raw": _raw(draft)})
    if draft["proactive"]:
        _record_proactive(rcpts)
    return {"sent": True, "from": common.own_account(), "to": draft["to"], "cc": draft["cc"],
            "message_id": (res or {}).get("id"), "approved_send": bool(outside), "proactive": draft["proactive"]}


def reply(args: Dict[str, Any], approval_token: Optional[str] = None) -> Dict[str, Any]:
    """Reply in the thread of a message in Casey's inbox. The original sender may always be answered."""
    message_id = str(args.get("message_id") or "").strip()
    if not message_id:
        raise common.PolicyError("missing message_id to reply to")
    orig = gmail.headers_for_reply(message_id)
    sender = normalize_recipients(orig.get("from"), "from")
    sender_addr = sender[0] if sender else ""
    merged = dict(args)
    merged.setdefault("to", sender_addr)
    subj = orig.get("subject") or ""
    merged.setdefault("subject", subj if re.match(r"^\s*re\s*:", subj, re.I) else f"Re: {subj}".strip())
    merged["proactive"] = False
    draft = build_draft(merged)
    rcpts = _recipients(draft)
    _check_suppressed(rcpts)
    outside = off_allowlist(rcpts, reply_to_sender=sender_addr)
    if outside:
        if not approval_token:
            raise common.PolicyError("extra recipient(s) need approval (" + ", ".join(outside) + "): propose first")
        approvals.consume(approval_token, "email", draft)
    body = {"raw": _raw(draft, orig), "threadId": orig.get("thread_id")}
    res = common.http_json("POST", f"{_API}/messages/send", headers=auth.OWN.headers(), body=body)
    return {"sent": True, "reply": True, "from": common.own_account(), "to": draft["to"], "cc": draft["cc"],
            "thread_id": orig.get("thread_id"), "message_id": (res or {}).get("id")}
