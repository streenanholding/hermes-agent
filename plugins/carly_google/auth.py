"""Google OAuth for TWO accounts, each with its own consent, refresh token and state file.

* RICK (CARLY_GOOGLE_ACCOUNT, rick@finverified.ai): READ-ONLY scopes. Unchanged from Phase 2.
* OWN  (CARLY_OWN_ACCOUNT, default carly@finverified.ai): Carly's own mailbox and calendar
  (gmail.send, gmail.compose, gmail.readonly, calendar.events).

No service account, no domain-wide delegation: each token can only act as the account that
completed consent, and consent is rejected unless that account is the expected one. Both
connections reuse the existing Google OAuth client (GOOGLE_OAUTH_CLIENT_ID / _SECRET) and the
same redirect URI (/google-callback); an own-connection state starts with "own." so the callback
can tell them apart without registering a new redirect URI.
"""

from __future__ import annotations

import secrets
import time
from typing import Dict, Tuple
from urllib.parse import urlencode

from . import common

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]
OWN_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]
OWN_STATE_PREFIX = "own."
_TOKEN_URL = "https://oauth2.googleapis.com/token"


class Connection:
    """One Google account: its scopes, state files, expected address and access-token cache."""

    def __init__(self, name: str, scopes: list, refresh_file: str, state_file: str, connect_path: str):
        self.name, self.scopes = name, scopes
        self.refresh_file, self.state_file, self.connect_path = refresh_file, state_file, connect_path
        self.cache: Dict[str, float | str] = {}

    def account(self) -> str:
        return common.own_account() if self.name == "own" else common.account()

    def connect_url(self) -> str:
        return public_url() + self.connect_path

    def refresh_token(self) -> str:
        rt = common.load_state(self.refresh_file, {}).get("refresh_token", "")
        if not rt:
            raise common.PolicyError(f"Google ({self.name}) is not connected yet: Rick must complete the one-time "
                                     f"sign-in at {self.connect_url()}")
        return rt

    def connected(self) -> bool:
        try:
            self.refresh_token()
            return True
        except common.PolicyError:
            return False

    def authorize_url(self) -> str:
        state = (OWN_STATE_PREFIX if self.name == "own" else "") + secrets.token_urlsafe(24)
        common.save_state(self.state_file, {"state": state})
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
            "client_id": _client()["client_id"], "redirect_uri": redirect_uri(), "response_type": "code",
            "scope": " ".join(self.scopes), "access_type": "offline", "prompt": "consent",
            "login_hint": self.account(), "state": state})

    def handle_callback(self, code: str, state: str) -> bool:
        saved = common.load_state(self.state_file, {})
        if not saved.get("state") or not secrets.compare_digest(saved["state"], state or ""):
            return False
        common.save_state(self.state_file, {})  # single use
        tok = common.http_json("POST", _TOKEN_URL, form={**_client(), "code": code, "redirect_uri": redirect_uri(),
                                                         "grant_type": "authorization_code"})
        if not tok.get("refresh_token") or not tok.get("access_token"):
            return False
        granted = set(str(tok.get("scope", "")).split())
        if not set(self.scopes).issubset(granted):
            return False  # every requested scope must be granted
        who = common.http_json("GET", "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                               headers={"Authorization": "Bearer " + tok["access_token"]})
        if str(who.get("emailAddress", "")).lower() != self.account().lower():
            return False  # wrong Google account signed in: refuse, store nothing
        common.save_state(self.refresh_file, {"refresh_token": tok["refresh_token"]})  # volume, mode 600, never printed
        self.cache.clear()
        return True

    def access_token(self) -> str:
        if self.cache.get("expires_at", 0) > time.time():
            return str(self.cache["access_token"])
        tok = common.http_json("POST", _TOKEN_URL, form={**_client(), "refresh_token": self.refresh_token(),
                                                         "grant_type": "refresh_token"})
        self.cache["access_token"] = tok["access_token"]
        self.cache["expires_at"] = time.time() + int(tok.get("expires_in", 3600)) - 60
        return str(self.cache["access_token"])

    def headers(self) -> Dict[str, str]:
        return {"Authorization": "Bearer " + self.access_token()}


RICK = Connection("rick", SCOPES, "google_refresh.json", "google_oauth_state.json", "/google-connect")
OWN = Connection("own", OWN_SCOPES, "google_own_refresh.json", "google_own_oauth_state.json", "/google-own-connect")
_cache = RICK.cache  # kept for tests / callers that clear Rick's cache


def public_url() -> str:
    return common.env_required("CARLY_PUBLIC_URL").rstrip("/")


def redirect_uri() -> str:
    return public_url() + "/google-callback"


def _client() -> Dict[str, str]:
    return {"client_id": common.env_required("GOOGLE_OAUTH_CLIENT_ID"),
            "client_secret": common.env_required("GOOGLE_OAUTH_CLIENT_SECRET")}


# Rick's read-only connection (module-level API unchanged).
def refresh_token() -> str:
    return RICK.refresh_token()


def connected() -> bool:
    return RICK.connected()


def authorize_url() -> str:
    return RICK.authorize_url()


def access_token() -> str:
    return RICK.access_token()


def headers() -> Dict[str, str]:
    return RICK.headers()


def handle_callback(code: str, state: str) -> bool:
    """Route a /google-callback to the right connection by its state prefix."""
    if (state or "").startswith(OWN_STATE_PREFIX):
        return OWN.handle_callback(code, state)
    return RICK.handle_callback(code, state)
