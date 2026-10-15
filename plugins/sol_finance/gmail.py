"""Gmail: gmail.readonly for sol@finverified.ai only (user OAuth, no domain-wide delegation).

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
# Hard-coded: report email may only ever go to these two addresses.
ALLOWED_RECIPIENTS = ("rick@finverified.ai", "ncoy@finverified.ai")


class GmailPolicyError(PermissionError):
    pass


def _phase() -> int:
    try:
        return int(os.environ.get("SOL_PHASE", "1") or 1)
    except ValueError:
        return 1


def scopes() -> str:
    """Phase 1: readonly. Phase 2+: readonly plus send."""
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


def send_report(subject: str, html_body: str) -> Dict[str, Any]:
    """Email an HTML report from sol@finverified.ai to the fixed allowlist (Phase 2+ only).

    No CC, BCC, attachments or caller-chosen recipients. The body is PII-scrubbed first.
    """
    if _phase() < 2:
        raise GmailPolicyError("Report email is disabled until Phase 2 (SOL_PHASE >= 2)")
    recipients = list(ALLOWED_RECIPIENTS)
    bad = [r for r in recipients if r not in ALLOWED_RECIPIENTS]
    if bad:
        raise GmailPolicyError("Recipient is not in the allowlist; nothing was sent")
    subject = pii.scrub(str(subject or "")).strip()
    if not subject or "\r" in subject or "\n" in subject:
        raise GmailPolicyError("Subject must be a single non-empty line")
    msg = EmailMessage()
    msg["From"] = MAILBOX
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content("This report is HTML. Please view it in an HTML-capable mail client.")
    msg.add_alternative(pii.scrub(str(html_body or "")), subtype="html")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    common.http_json("POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                     headers={"Authorization": "Bearer " + _access()}, body={"raw": raw})
    return {"sent": True, "to": recipients, "subject": subject}


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
