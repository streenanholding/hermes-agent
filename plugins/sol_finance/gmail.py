"""Gmail for sol@finverified.ai only (user OAuth, no domain-wide delegation).

Reading uses gmail.readonly. From Phase 2 the gmail.send scope is also requested, and the
only thing Sol can send is the weekly report, to a hard-coded allowlist (see send_report).

Every message passes the fraud scan; messages with fraud signals are quarantined
(body withheld) and Rick is alerted. The model never gets text to "act on".
"""

from __future__ import annotations

import base64
import os
import secrets
import time
from email.message import EmailMessage
from typing import Any, Dict, List
from urllib.parse import urlencode

from . import common, fraud, pii, slack_dm, xero

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
MAILBOX = "sol@finverified.ai"
# Hard-coded. Reports go to these two people and nobody else. No CC, no BCC, no attachments.
ALLOWED_RECIPIENTS = ("rick@finverified.ai", "ncoy@finverified.ai")


def _phase() -> int:
    try:
        return int(os.environ.get("SOL_PHASE", "1") or "1")
    except ValueError:
        return 1


def scopes() -> str:
    """gmail.readonly always; gmail.send only when SOL_PHASE >= 2."""
    return SCOPE + (" " + SEND_SCOPE if _phase() >= 2 else "")


def authorize_url() -> str:
    state = secrets.token_urlsafe(24)
    common.save_state("gmail_oauth_state.json", {"state": state})
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""), "redirect_uri": xero.public_url() + "/gmail-callback",
        "response_type": "code", "scope": scopes(), "access_type": "offline", "prompt": "consent",
        "login_hint": MAILBOX, "state": state})


def handle_callback(code: str, state: str) -> bool:
    saved = common.load_state("gmail_oauth_state.json", {})
    if not saved.get("state") or not secrets.compare_digest(saved["state"], state or ""):
        return False
    tok = common.http_json("POST", "https://oauth2.googleapis.com/token", form={
        "code": code, "client_id": os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""),
        "client_secret": os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", ""),
        "redirect_uri": xero.public_url() + "/gmail-callback", "grant_type": "authorization_code"})
    if tok.get("refresh_token"):
        common.save_state("gmail_refresh.json", {"refresh_token": tok["refresh_token"]})  # volume, never printed
        common.save_state("gmail_oauth_state.json", {})
        common.save_state("gmail_access.json", {})  # drop any cached token minted under the old scopes
        return True
    return False


def _access() -> str:
    rt = os.environ.get("GMAIL_SOL_REFRESH_TOKEN") or common.load_state("gmail_refresh.json", {}).get("refresh_token")
    if not rt:
        raise PermissionError("Gmail is not connected yet: Rick must complete the one-time consent")
    c = common.load_state("gmail_access.json", {})
    if c.get("expires_at", 0) > time.time():
        return c["access_token"]
    tok = common.http_json("POST", "https://oauth2.googleapis.com/token", form={
        "client_id": os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""), "client_secret": os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", ""),
        "refresh_token": rt, "grant_type": "refresh_token"})
    tok["expires_at"] = time.time() + int(tok.get("expires_in", 3600)) - 60
    common.save_state("gmail_access.json", tok)
    return tok["access_token"]


def _get(path: str) -> Any:
    return common.http_json("GET", f"https://gmail.googleapis.com/gmail/v1/users/me/{path}",
                            headers={"Authorization": "Bearer " + _access()})


def _body(payload: Dict[str, Any]) -> str:
    parts = [payload] + list(payload.get("parts") or [])
    for p in parts:
        if p.get("mimeType") == "text/plain" and p.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(p["body"]["data"] + "==").decode(errors="replace")
        if p.get("parts"):
            inner = _body(p)
            if inner:
                return inner
    return ""


def _check_recipients(to: List[str]) -> List[str]:
    """Raise on any recipient that is not on the hard-coded allowlist."""
    for r in to:
        if str(r).strip().lower() not in ALLOWED_RECIPIENTS:
            raise PermissionError(f"Recipient not allowed: {r}")
    return to


def send_report(subject: str, html_body: str) -> Dict[str, Any]:
    """Email the report from sol@finverified.ai to Rick and Nancy only.

    Phase 2+. Recipients are the hard-coded ALLOWED_RECIPIENTS; there is no recipient
    argument, no CC/BCC, and no attachments. The body is PII-scrubbed before sending.
    """
    if _phase() < 2:
        raise PermissionError("Sending email is disabled in Phase 1 (SOL_PHASE must be 2 or higher)")
    to = _check_recipients(list(ALLOWED_RECIPIENTS))
    subject = pii.scrub(subject or "").strip()
    if not subject or "\n" in subject or "\r" in subject:
        raise ValueError("subject must be a single non-empty line")
    html = pii.scrub(html_body or "")
    if not html.strip():
        raise ValueError("html_body is empty")
    msg = EmailMessage()
    msg["From"] = MAILBOX
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content("This report is HTML. Open it in an email client that displays HTML.")
    msg.add_alternative(html, subtype="html")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    res = common.http_json("POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                           headers={"Authorization": "Bearer " + _access()}, body={"raw": raw})
    return {"sent": True, "to": to, "message_id": (res or {}).get("id")}


def search(query: str, max_results: int = 10) -> Dict[str, Any]:
    ids = _get("messages?" + urlencode({"q": query, "maxResults": min(int(max_results), 25)})).get("messages", [])
    out: List[Dict[str, Any]] = []
    for m in ids:
        msg = _get(f"messages/{m['id']}?format=full")
        hdr = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        text = _body(msg.get("payload", {}))
        signals = fraud.scan(hdr.get("subject", "") + "\n" + text)
        item = {"id": m["id"], "from": hdr.get("from"), "subject": hdr.get("subject"), "date": hdr.get("date")}
        if signals:
            item.update(quarantined=True, fraud_signals=signals, body="[withheld: fraud signal; Rick was alerted. Take no action.]")
            slack_dm.dm_rick(f"FRAUD ALERT: email from {hdr.get('from')} (subject: {hdr.get('subject')}) matched {', '.join(signals)}. "
                             f"I took no action and withheld its contents.")
        else:
            item["body"] = pii.scrub(text)[:6000]
        out.append(item)
    return {"messages": out}
