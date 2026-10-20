"""Carly's OWN mailbox (carly@finverified.ai): read, draft, send. Rules are enforced here, in code.

* From is always CARLY_OWN_ACCOUNT. There is no from argument, no attachment argument, no BCC
  and no forward action; a "Fwd:" subject is refused.
* Recipients on CARLY_SEND_ALLOWLIST (default rick@, sol@, seraphine@finverified.ai) are sent
  directly. Any other recipient needs a single-use approval token: propose -> Rick's yes
  (confirm) -> send with the token. See approvals.py.
Rick's mailbox is never written to; it has its own read-only connection (gmail.py, auth.RICK).
"""

from __future__ import annotations

import base64
import os
import re
from email.message import EmailMessage
from email.utils import getaddresses
from typing import Any, Dict, List, Optional

from . import approvals, auth, common

DEFAULT_ALLOWLIST = "rick@finverified.ai,sol@finverified.ai,seraphine@finverified.ai"
_API = "https://gmail.googleapis.com/gmail/v1/users/me"
_ADDR = re.compile(r"^[^@\s<>,;\"']+@[^@\s<>,;\"']+\.[^@\s<>,;\"']+$")
MAX_RECIPIENTS = 20


def allowlist() -> List[str]:
    raw = os.environ.get("CARLY_SEND_ALLOWLIST")
    raw = DEFAULT_ALLOWLIST if raw is None else raw
    return [a.strip().lower() for a in raw.split(",") if a.strip()]


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


def off_allowlist(addresses: List[str]) -> List[str]:
    allowed = set(allowlist())
    return [a for a in addresses if a not in allowed]


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
        raise common.PolicyError("forwarding is not allowed: Carly never forwards messages from Rick's mailbox")
    if not body.strip():
        raise common.PolicyError("body is empty")
    if len(body) > 20000:
        raise common.PolicyError("body too long (max 20000 characters)")
    return {"to": to, "cc": cc, "subject": subject, "body": body}


def _raw(draft: Dict[str, Any]) -> str:
    msg = EmailMessage()
    msg["From"] = common.own_account()  # always her own address; never an argument
    msg["To"] = ", ".join(draft["to"])
    if draft["cc"]:
        msg["Cc"] = ", ".join(draft["cc"])
    msg["Subject"] = draft["subject"]
    msg.set_content(draft["body"])
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def _recipients(draft: Dict[str, Any]) -> List[str]:
    return draft["to"] + draft["cc"]


def propose(args: Dict[str, Any]) -> Dict[str, Any]:
    draft = build_draft(args)
    outside = off_allowlist(_recipients(draft))
    item = approvals.propose("email", draft)
    return {"approval_token": item["token"], "from": common.own_account(), "draft": draft,
            "recipients_needing_approval": outside, "expires_in_hours": item["expires_in_hours"],
            "next": "Show Rick the full draft (to, cc, subject, body). Only after he says yes in chat, call confirm "
                    "with this token, then send with approval_token. If he edits it, propose again."}


def create_draft(args: Dict[str, Any]) -> Dict[str, Any]:
    draft = build_draft(args)
    res = common.http_json("POST", f"{_API}/drafts", headers=auth.OWN.headers(), body={"message": {"raw": _raw(draft)}})
    return {"drafted": True, "draft_id": (res or {}).get("id"), "from": common.own_account(), "draft": draft,
            "needs_approval_to_send": off_allowlist(_recipients(draft))}


def send(args: Dict[str, Any], approval_token: Optional[str] = None) -> Dict[str, Any]:
    draft = build_draft(args)
    outside = off_allowlist(_recipients(draft))
    if outside:
        if not approval_token:
            raise common.PolicyError("recipient(s) not on the allowlist (" + ", ".join(outside) + "): use propose, get "
                                     "Rick's yes, confirm, then send with approval_token")
        approvals.consume(approval_token, "email", draft)  # single use; marks the token used
    res = common.http_json("POST", f"{_API}/messages/send", headers=auth.OWN.headers(), body={"raw": _raw(draft)})
    return {"sent": True, "from": common.own_account(), "to": draft["to"], "cc": draft["cc"],
            "message_id": (res or {}).get("id"), "approved_send": bool(outside)}
