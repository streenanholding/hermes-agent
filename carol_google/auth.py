"""Google OAuth for ONE mailbox (CAROL_EMAIL), user consent + refresh token.

No service account and no domain-wide delegation: the token can only ever act as
the account that completed consent, and consent is rejected unless that account
is CAROL_EMAIL. Reuses the existing Google OAuth client (GOOGLE_OAUTH_CLIENT_ID /
GOOGLE_OAUTH_CLIENT_SECRET). Gmail plus Drive; Drive is confined in code to the Pay✓erified shared drive (CAROL_DRIVE_ROOT_ID). No Calendar.
"""

from __future__ import annotations

import os
import secrets
import time
from typing import Dict
from urllib.parse import urlencode

from . import common

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive",  # confined in code to CAROL_DRIVE_ROOT_ID
]
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_cache: Dict[str, float | str] = {}


def public_url() -> str:
    return common.env_required("CAROL_PUBLIC_URL").rstrip("/")


def redirect_uri() -> str:
    return public_url() + "/google-callback"


def _client() -> Dict[str, str]:
    return {"client_id": common.env_required("GOOGLE_OAUTH_CLIENT_ID"),
            "client_secret": common.env_required("GOOGLE_OAUTH_CLIENT_SECRET")}


def refresh_token() -> str:
    rt = os.environ.get("CAROL_GOOGLE_REFRESH_TOKEN", "").strip() or common.load_state("google_refresh.json", {}).get("refresh_token", "")
    if not rt:
        raise common.PolicyError("Google is not connected yet: Rick must complete the one-time sign-in as the Carol account")
    return rt


def connected() -> bool:
    try:
        refresh_token()
        return True
    except common.PolicyError:
        return False


def authorize_url() -> str:
    state = secrets.token_urlsafe(24)
    common.save_state("google_oauth_state.json", {"state": state})
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": _client()["client_id"], "redirect_uri": redirect_uri(), "response_type": "code",
        "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent",
        "login_hint": common.mailbox(), "state": state})


def handle_callback(code: str, state: str) -> bool:
    saved = common.load_state("google_oauth_state.json", {})
    if not saved.get("state") or not secrets.compare_digest(saved["state"], state or ""):
        return False
    common.save_state("google_oauth_state.json", {})  # single use
    tok = common.http_json("POST", _TOKEN_URL, form={**_client(), "code": code, "redirect_uri": redirect_uri(),
                                                     "grant_type": "authorization_code"})
    if not tok.get("refresh_token") or not tok.get("access_token"):
        return False
    who = common.http_json("GET", "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                           headers={"Authorization": "Bearer " + tok["access_token"]})
    if str(who.get("emailAddress", "")).lower() != common.mailbox().lower():
        return False  # wrong Google account signed in: refuse, store nothing
    common.save_state("google_refresh.json", {"refresh_token": tok["refresh_token"]})  # volume, mode 600, never printed
    _cache.clear()
    return True


def access_token() -> str:
    if _cache.get("expires_at", 0) > time.time():
        return str(_cache["access_token"])
    tok = common.http_json("POST", _TOKEN_URL, form={**_client(), "refresh_token": refresh_token(),
                                                     "grant_type": "refresh_token"})
    _cache["access_token"] = tok["access_token"]
    _cache["expires_at"] = time.time() + int(tok.get("expires_in", 3600)) - 60
    return str(_cache["access_token"])


def headers() -> Dict[str, str]:
    return {"Authorization": "Bearer " + access_token()}
