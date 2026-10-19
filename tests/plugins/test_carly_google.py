"""Carly read-only Google plugin: OAuth account lock, read-only tools, calendar ranges."""

import base64
import json

import pytest


@pytest.fixture
def cg(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("CARLY_GOOGLE_ACCOUNT", "rick@finverified.ai")
    monkeypatch.setenv("CARLY_PUBLIC_URL", "https://carly.example.app")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "cs")
    from plugins.carly_google import auth, common, tools

    state = {"who": "rick@finverified.ai"}

    def fake(method, url, *, headers=None, body=None, form=None, timeout=30):
        if url.endswith("/token"):
            if form.get("grant_type") == "authorization_code":
                return {"access_token": "a", "refresh_token": "r", "scope": " ".join(auth.SCOPES), "expires_in": 3600}
            return {"access_token": "a2", "expires_in": 3600}
        if url.endswith("/profile"):
            return {"emailAddress": state["who"]}
        if "messages?" in url:
            return {"messages": [{"id": "m1"}]}
        if "format=metadata" in url:
            return {"threadId": "t", "snippet": "hi", "labelIds": ["UNREAD"],
                    "payload": {"headers": [{"name": "Subject", "value": "S"}]}}
        if "format=full" in url:
            enc = base64.urlsafe_b64encode(b"hello").decode().rstrip("=")
            return {"payload": {"mimeType": "multipart/mixed", "parts": [
                {"mimeType": "multipart/alternative", "parts": [{"mimeType": "text/plain", "body": {"data": enc}}]}]}}
        if "calendar" in url:
            return {"items": [{"summary": "Opus CTO", "start": {"dateTime": "2026-10-21T10:00:00-04:00"},
                               "end": {"dateTime": "2026-10-21T11:00:00-04:00"},
                               "attendees": [{"email": "rick@finverified.ai", "self": True, "responseStatus": "accepted"}]},
                              {"status": "cancelled"}]}
        raise AssertionError(url)

    monkeypatch.setattr(common, "http_json", fake)
    auth._cache.clear()
    return auth, common, tools, state


def _connect(auth, common):
    auth.authorize_url()
    return auth.handle_callback("code", common.load_state("google_oauth_state.json", {})["state"])


def test_only_read_only_scopes(cg):
    auth, *_ = cg
    assert set(auth.SCOPES) == {"https://www.googleapis.com/auth/gmail.readonly",
                                "https://www.googleapis.com/auth/calendar.readonly"}


def test_not_connected_points_to_connect_link(cg):
    _, _, tools, _ = cg
    r = json.loads(tools.h_gmail({"action": "search", "query": "x"}))
    assert not r["success"] and "/google-connect" in r["error"]
    r = json.loads(tools.h_gmail({"action": "connect_link"}))
    assert r["url"] == "https://carly.example.app/google-connect" and r["connected"] is False


def test_wrong_account_and_bad_state_rejected(cg):
    auth, common, _, state = cg
    state["who"] = "someone@else.com"
    assert _connect(auth, common) is False and not auth.connected()
    assert auth.handle_callback("code", "nope") is False


def test_right_account_connects_once_and_reads(cg):
    auth, common, tools, state = cg
    state["who"] = "Rick@FinVerified.ai"
    assert _connect(auth, common) is True and auth.connected()
    r = json.loads(tools.h_gmail({"action": "search", "query": "is:unread"}))
    assert r["success"] and r["messages"][0]["unread"]
    r = json.loads(tools.h_gmail({"action": "read", "message_id": "m1"}))
    assert r["body"] == "hello" and r["untrusted"] is True


def test_calendar_events_and_limits(cg):
    auth, common, tools, _ = cg
    _connect(auth, common)
    r = json.loads(tools.h_calendar({"action": "events", "start": "2026-10-19", "end": "2026-10-26"}))
    assert len(r["events"]) == 1 and r["events"][0]["my_response"] == "accepted"
    assert r["time_min"].endswith("-04:00")
    r = json.loads(tools.h_calendar({"action": "events", "start": "2026-11-10", "end": "2026-11-11"}))
    assert r["time_min"].endswith("-05:00")
    r = json.loads(tools.h_calendar({"action": "events", "start": "2026-10-19", "end": "2027-01-26"}))
    assert not r["success"]


def test_no_write_actions(cg):
    _, _, tools, _ = cg
    for a in ("send", "send_draft", "create_draft", "delete", "trash", "modify", "mark_read"):
        assert not json.loads(tools.h_gmail({"action": a}))["success"]
    for a in ("create", "update", "delete", "rsvp"):
        assert not json.loads(tools.h_calendar({"action": a}))["success"]
