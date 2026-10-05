"""Xero OAuth (read scopes now) and the DRAFT-only write guard.

Phase 1 requests only .read scopes, so Xero itself rejects writes. `assert_draft`
is the code-level guard Phase 2 builds on: any payload whose Status is not DRAFT
is rejected before a request is made.
"""

from __future__ import annotations

import base64
import os
import secrets
import time
from typing import Any, Dict
from urllib.parse import urlencode

from . import common

AUTH_URL = "https://login.xero.com/identity/connect/authorize"
TOKEN_URL = "https://identity.xero.com/connect/token"
API = "https://api.xero.com/api.xro/2.0"
# Granular read scopes only (Xero apps created after 2026-03-02 cannot use the broad ones).
READ_SCOPES = " ".join([
    "offline_access",
    "accounting.settings.read",
    "accounting.contacts.read",
    "accounting.attachments.read",
    "accounting.budgets.read",
    "accounting.payments.read",
    "accounting.invoices.read",
    "accounting.banktransactions.read",
    "accounting.manualjournals.read",
    "accounting.reports.aged.read",
    "accounting.reports.balancesheet.read",
    "accounting.reports.banksummary.read",
    "accounting.reports.budgetsummary.read",
    "accounting.reports.executivesummary.read",
    "accounting.reports.profitandloss.read",
    "accounting.reports.trialbalance.read",
    "accounting.reports.taxreports.read",
    "accounting.reports.tenninetynine.read",
])
WRITE_ENABLED = os.environ.get("SOL_PHASE", "1") not in ("1", "")  # Phase 2+ only


class XeroPolicyError(PermissionError):
    pass


def public_url() -> str:
    if os.environ.get("SOL_PUBLIC_URL"):
        return os.environ["SOL_PUBLIC_URL"].rstrip("/")
    d = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
    return f"https://{d}" if d else ""


def redirect_uri() -> str:
    return public_url() + "/xero-callback"


def assert_draft(payload: Any) -> None:
    """Every Status field in a write payload must be exactly DRAFT, and one must exist."""
    found = []

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if str(k).lower() == "status":
                    found.append(v)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(payload)
    if not found:
        raise XeroPolicyError("Xero write rejected: payload has no Status; only Status=DRAFT is allowed")
    bad = [v for v in found if v != "DRAFT"]
    if bad:
        raise XeroPolicyError(f"Xero write rejected: Status {bad[0]!r} is not DRAFT")


def post_draft(endpoint: str, payload: Any) -> Any:
    assert_draft(payload)
    if not WRITE_ENABLED:
        raise XeroPolicyError("Xero writes are disabled until Phase 2 (Rick says go)")
    return _call("POST", endpoint, payload)


def authorize_url() -> str:
    state = secrets.token_urlsafe(24)
    common.save_state("xero_oauth_state.json", {"state": state, "at": time.time()})
    return AUTH_URL + "?" + urlencode({"response_type": "code", "client_id": os.environ.get("XERO_CLIENT_ID", ""),
                                       "redirect_uri": redirect_uri(), "scope": READ_SCOPES, "state": state})


def _basic() -> str:
    raw = f"{os.environ.get('XERO_CLIENT_ID','')}:{os.environ.get('XERO_CLIENT_SECRET','')}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def handle_callback(code: str, state: str) -> bool:
    saved = common.load_state("xero_oauth_state.json", {})
    if not saved.get("state") or not secrets.compare_digest(saved["state"], state or ""):
        return False
    tok = common.http_json("POST", TOKEN_URL, headers={"Authorization": _basic()},
                           form={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri()})
    tok["expires_at"] = time.time() + int(tok.get("expires_in", 1800)) - 60
    common.save_state("xero_oauth_state.json", {})
    # /xero-connect is public, so only keep tokens that are for the FinVerified organisation.
    conns = common.http_json("GET", "https://api.xero.com/connections",
                             headers={"Authorization": "Bearer " + tok["access_token"]})
    want = os.environ.get("SOL_XERO_ORG_NAME", "FinVerified").lower()
    if not any(want in str(c.get("tenantName", "")).lower() for c in conns or []):
        return False
    common.save_state("xero_tokens.json", tok)
    return True


def _token() -> str:
    tok = common.load_state("xero_tokens.json", {})
    if not tok.get("refresh_token"):
        raise XeroPolicyError("Xero is not connected yet: Rick must open the Xero consent link")
    if tok.get("expires_at", 0) < time.time():
        new = common.http_json("POST", TOKEN_URL, headers={"Authorization": _basic()},
                               form={"grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
        new["expires_at"] = time.time() + int(new.get("expires_in", 1800)) - 60
        common.save_state("xero_tokens.json", new)
        tok = new
    return tok["access_token"]


def _tenant() -> str:
    return _tenant_info()["tenantId"]


def _call(method: str, endpoint: str, body: Any = None) -> Any:
    return common.http_json(method, f"{API}/{endpoint.lstrip('/')}",
                            headers={"Authorization": "Bearer " + _token(), "xero-tenant-id": _tenant(),
                                     "Accept": "application/json"}, body=body)


def read(endpoint: str) -> Any:
    first = endpoint.lstrip("/").split("/")[0].split("?")[0]
    if first not in {"Accounts", "Contacts", "Invoices", "BankTransactions", "ManualJournals", "Reports",
                     "Organisation", "Items", "Payments"}:
        raise XeroPolicyError(f"Xero endpoint not readable: {first}")
    return _call("GET", endpoint)


def org_name() -> str:
    """Name only of the connected organisation."""
    return _tenant_info()["tenantName"]


def _tenant_info() -> Dict[str, Any]:
    conns = common.http_json("GET", "https://api.xero.com/connections",
                             headers={"Authorization": "Bearer " + _token()})
    if not conns:
        raise XeroPolicyError("no Xero organisation connected")
    return conns[0]
