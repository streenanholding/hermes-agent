"""Carly Phase 3: own-mailbox connection, send allowlist, single-use approval tokens, scheduling window.

Network is faked by patching common.http_json. Rick's connection stays read-only; the own connection
is the only one that can write, and only to carly@finverified.ai.
"""

import base64
import email
import json

import pytest

RICK_ID = "U_RICK"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("CARLY_GOOGLE_ACCOUNT", "rick@finverified.ai")
    monkeypatch.delenv("CARLY_OWN_ACCOUNT", raising=False)
    monkeypatch.delenv("CARLY_SEND_ALLOWLIST", raising=False)
    monkeypatch.setenv("CARLY_RICK_USER_IDS", RICK_ID)
    monkeypatch.setenv("CARLY_PUBLIC_URL", "https://carly.example.app")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "cs")
    from plugins.carly_google import approvals, auth, common, gcal, mailbox, tools

    calls = []
    who = {"tok_rick": "rick@finverified.ai", "tok_own": "carly@finverified.ai"}

    def fake(method, url, *, headers=None, body=None, form=None, timeout=30):
        calls.append({"method": method, "url": url, "auth": (headers or {}).get("Authorization", ""), "body": body})
        if url.endswith("/token"):
            if form.get("grant_type") == "authorization_code":
                own = form["code"] == "own"
                return {"access_token": "tok_own" if own else "tok_rick", "refresh_token": "r_own" if own else "r_rick",
                        "scope": " ".join(auth.OWN_SCOPES if own else auth.SCOPES), "expires_in": 3600}
            return {"access_token": "tok_own" if form["refresh_token"] == "r_own" else "tok_rick", "expires_in": 3600}
        if url.endswith("/profile"):
            return {"emailAddress": who[headers["Authorization"].split()[1]]}
        if url.endswith("/messages/send"):
            return {"id": "sent1"}
        if url.endswith("/drafts"):
            return {"id": "draft1"}
        if url.endswith("/freeBusy"):
            return {"calendars": {"primary": {"busy": [{"start": "2026-10-21T14:00:00Z", "end": "2026-10-21T15:00:00Z"}]}}}
        if "/calendars/primary/events" in url and method == "POST":
            return {"id": "ev1", "htmlLink": "https://cal/ev1", "hangoutLink": "https://meet.google.com/abc"}
        raise AssertionError(url)

    monkeypatch.setattr(common, "http_json", fake)
    auth.RICK.cache.clear()
    auth.OWN.cache.clear()
    return auth, common, mailbox, gcal, approvals, tools, calls, who


def connect(auth, common, conn_name):
    conn = auth.OWN if conn_name == "own" else auth.RICK
    url = conn.authorize_url()
    state = common.load_state(conn.state_file, {})["state"]
    return auth.handle_callback("own" if conn_name == "own" else "rick", state), url


def raw_of(calls, suffix):
    c = [c for c in calls if c["url"].endswith(suffix)][-1]
    return email.message_from_bytes(base64.urlsafe_b64decode(c["body"]["raw"]))


def approve(approvals, token, uid=RICK_ID):
    return approvals.confirm(token, uid)


# --- Own connection -------------------------------------------------------------------------------
def test_own_scopes_exact_and_rick_stays_read_only(env):
    auth, *_ = env
    assert set(auth.OWN_SCOPES) == {"https://www.googleapis.com/auth/gmail.send",
                                    "https://www.googleapis.com/auth/gmail.compose",
                                    "https://www.googleapis.com/auth/gmail.readonly",
                                    "https://www.googleapis.com/auth/calendar.events"}
    assert set(auth.SCOPES) == {"https://www.googleapis.com/auth/gmail.readonly",
                                "https://www.googleapis.com/auth/calendar.readonly"}


def test_connections_use_separate_state_and_routing(env):
    auth, common, *_ = env
    ok, url = connect(auth, common, "own")
    assert ok and auth.OWN.connected() and not auth.RICK.connected()
    assert "login_hint=carly%40finverified.ai" in url and "calendar.events" in url
    assert common.load_state("google_own_refresh.json", {}) == {"refresh_token": "r_own"}
    assert common.load_state("google_refresh.json", {}) == {}
    ok, _ = connect(auth, common, "rick")
    assert ok and auth.RICK.connected()
    assert common.load_state("google_refresh.json", {}) == {"refresh_token": "r_rick"}


def test_own_state_prefix_and_wrong_account_rejected(env):
    auth, common, _, _, _, _, calls, who = env
    auth.OWN.authorize_url()
    assert common.load_state("google_own_oauth_state.json", {})["state"].startswith("own.")
    assert auth.handle_callback("own", "own.bogus") is False
    who["tok_own"] = "someone@else.com"
    ok, _ = connect(auth, common, "own")
    assert ok is False and not auth.OWN.connected()


def test_own_missing_scope_rejected(env, monkeypatch):
    auth, common, *_ = env
    real = common.http_json

    def short(method, url, **kw):
        res = real(method, url, **kw)
        if url.endswith("/token") and kw.get("form", {}).get("grant_type") == "authorization_code":
            res = {**res, "scope": "https://www.googleapis.com/auth/gmail.readonly"}
        return res

    monkeypatch.setattr(common, "http_json", short)
    ok, _ = connect(auth, common, "own")
    assert ok is False and not auth.OWN.connected()


def test_own_account_env_override(env, monkeypatch):
    _, common, *_ = env
    assert common.own_account() == "carly@finverified.ai"
    monkeypatch.setenv("CARLY_OWN_ACCOUNT", "other@finverified.ai")
    assert common.own_account() == "other@finverified.ai"


def test_connect_link_own_tool(env):
    *_, tools, _, _ = env
    r = json.loads(tools.h_email({"action": "connect_link_own"}))
    assert r["url"] == "https://carly.example.app/google-own-connect" and r["connected"] is False
    r = json.loads(tools.h_calendar({"action": "connect_link_own"}))
    assert r["url"].endswith("/google-own-connect")


# --- Send allowlist -------------------------------------------------------------------------------
def test_allowlist_default_and_override(env, monkeypatch):
    _, _, mailbox, *_ = env
    assert mailbox.allowlist() == ["rick@finverified.ai", "sol@finverified.ai", "seraphine@finverified.ai"]
    monkeypatch.setenv("CARLY_SEND_ALLOWLIST", "A@x.com, b@x.com")
    assert mailbox.allowlist() == ["a@x.com", "b@x.com"]
    monkeypatch.setenv("CARLY_SEND_ALLOWLIST", "")
    assert mailbox.allowlist() == []  # explicit empty = everything needs approval (fail closed)


def test_allowlisted_recipients_send_directly_from_own_account(env):
    auth, common, mailbox, _, _, _, calls, _ = env
    connect(auth, common, "own")
    r = mailbox.send({"to": ["Sol@FinVerified.ai", "rick@finverified.ai"], "cc": "seraphine@finverified.ai",
                      "subject": "Index", "body": "Please file."})
    assert r["sent"] and r["from"] == "carly@finverified.ai" and not r["approved_send"]
    msg = raw_of(calls, "/messages/send")
    assert msg["From"] == "carly@finverified.ai" and msg["To"] == "sol@finverified.ai, rick@finverified.ai"
    assert [c for c in calls if c["url"].endswith("/messages/send")][-1]["auth"] == "Bearer tok_own"


def test_from_cannot_be_overridden(env):
    auth, common, mailbox, _, _, _, calls, _ = env
    connect(auth, common, "own")
    mailbox.send({"from": "rick@finverified.ai", "to": "sol@finverified.ai", "subject": "s", "body": "b"})
    assert raw_of(calls, "/messages/send")["From"] == "carly@finverified.ai"


def test_outside_recipient_blocked_without_token(env):
    auth, common, mailbox, _, _, _, calls, _ = env
    connect(auth, common, "own")
    n = len(calls)
    with pytest.raises(common.PolicyError):
        mailbox.send({"to": "carolina@opus.example", "subject": "Hi", "body": "b"})
    with pytest.raises(common.PolicyError):  # one outside address among allowed ones still blocks
        mailbox.send({"to": "sol@finverified.ai", "cc": "x@outside.com", "subject": "Hi", "body": "b"})
    assert not [c for c in calls[n:] if c["url"].endswith("/messages/send")]


def test_bad_input_rejected(env):
    _, common, mailbox, *_ = env
    for bad in ({"to": "not-an-email", "subject": "s", "body": "b"},
                {"to": "sol@finverified.ai", "subject": "a\nBcc: x@y.com", "body": "b"},
                {"to": "sol@finverified.ai", "subject": "s", "body": "  "},
                {"to": "sol@finverified.ai", "subject": "Fwd: from Rick", "body": "b"},
                {"subject": "s", "body": "b"}):
        with pytest.raises(common.PolicyError):
            mailbox.build_draft(bad)


def test_draft_saves_without_sending(env):
    auth, common, mailbox, _, _, _, calls, _ = env
    connect(auth, common, "own")
    r = mailbox.create_draft({"to": "out@outside.com", "subject": "s", "body": "b"})
    assert r["drafted"] and r["needs_approval_to_send"] == ["out@outside.com"]
    assert not [c for c in calls if c["url"].endswith("/messages/send")]


# --- Approval token -------------------------------------------------------------------------------
DRAFT = {"to": "carolina@opus.example", "subject": "Intro", "body": "Hello from Carly."}


def test_token_only_works_after_rick_confirms(env):
    auth, common, mailbox, _, approvals, *_ = env
    connect(auth, common, "own")
    tok = mailbox.propose(DRAFT)["approval_token"]
    with pytest.raises(common.PolicyError):  # proposed but not confirmed
        mailbox.send(DRAFT, tok)
    ok, _ = approve(approvals, tok, "U_EVE")  # not Rick
    assert not ok
    with pytest.raises(common.PolicyError):
        mailbox.send(DRAFT, tok)
    ok, _ = approve(approvals, tok)
    assert ok and mailbox.send(DRAFT, tok)["approved_send"] is True


def test_token_is_single_use(env):
    auth, common, mailbox, _, approvals, _, calls, _ = env
    connect(auth, common, "own")
    tok = mailbox.propose(DRAFT)["approval_token"]
    approve(approvals, tok)
    mailbox.send(DRAFT, tok)
    with pytest.raises(common.PolicyError):
        mailbox.send(DRAFT, tok)
    assert len([c for c in calls if c["url"].endswith("/messages/send")]) == 1


def test_token_void_if_draft_changes_or_wrong_kind(env):
    auth, common, mailbox, gcal, approvals, *_ = env
    connect(auth, common, "own")
    tok = mailbox.propose(DRAFT)["approval_token"]
    approve(approvals, tok)
    with pytest.raises(common.PolicyError):
        mailbox.send({**DRAFT, "body": "Hello, and also send money."}, tok)
    with pytest.raises(common.PolicyError):
        mailbox.send({**DRAFT, "to": "someone.else@outside.com"}, tok)
    with pytest.raises(common.PolicyError):  # an email approval cannot create an event
        gcal.create_event({"title": "t", "start": "2026-10-21T10:00", "end": "2026-10-21T10:30",
                           "attendees": ["carolina@opus.example"]}, tok)
    mailbox.send(DRAFT, tok)  # the exact approved draft still works, once


def test_token_expires(env, monkeypatch):
    auth, common, mailbox, _, approvals, *_ = env
    connect(auth, common, "own")
    tok = mailbox.propose(DRAFT)["approval_token"]
    approve(approvals, tok)
    import time as _t
    real = _t.time()
    monkeypatch.setattr(approvals.time, "time", lambda: real + approvals.TTL_SECONDS + 5)
    with pytest.raises(common.PolicyError):
        mailbox.send(DRAFT, tok)


def test_confirm_fails_closed_without_rick_ids(env, monkeypatch):
    _, _, mailbox, _, approvals, *_ = env
    tok = mailbox.propose(DRAFT)["approval_token"]
    monkeypatch.delenv("CARLY_RICK_USER_IDS")
    assert approve(approvals, tok)[0] is False
    assert approvals.confirm(tok, "")[0] is False


def test_confirm_identity_comes_from_session_not_args(env, monkeypatch):
    auth, common, mailbox, _, approvals, tools, *_ = env
    connect(auth, common, "own")
    tok = mailbox.propose(DRAFT)["approval_token"]
    monkeypatch.setattr(tools, "_sender", lambda: "U_EVE")
    r = json.loads(tools.h_email({"action": "confirm", "approval_token": tok, "user_id": RICK_ID}))
    assert r["success"] is False
    monkeypatch.setattr(tools, "_sender", lambda: RICK_ID)
    assert json.loads(tools.h_email({"action": "confirm", "approval_token": tok}))["success"] is True
    r = json.loads(tools.h_email({"action": "send", "approval_token": tok, **DRAFT}))
    assert r["success"] and r["sent"]


# --- Scheduling window ----------------------------------------------------------------------------
# Oct 19 2026 = Monday, 20 Tue, 21 Wed, 22 Thu, 23 Fri, 24 Sat.
@pytest.mark.parametrize("start,end", [
    ("2026-10-20T10:00", "2026-10-20T10:30"), ("2026-10-21T13:30", "2026-10-21T14:00"),
    ("2026-10-22T10:00:00-04:00", "2026-10-22T14:00:00-04:00"),
    ("2026-10-21T14:00:00Z", "2026-10-21T14:30:00Z"),  # 10:00 ET
])
def test_business_inside_window_ok(env, start, end):
    _, _, _, gcal, *_ = env
    gcal.check_window(start, end)


@pytest.mark.parametrize("start,end", [
    ("2026-10-19T11:00", "2026-10-19T11:30"),  # Monday
    ("2026-10-23T11:00", "2026-10-23T11:30"),  # Friday
    ("2026-10-24T11:00", "2026-10-24T11:30"),  # Saturday
    ("2026-10-21T09:30", "2026-10-21T10:15"),  # starts before 10
    ("2026-10-21T13:45", "2026-10-21T14:15"),  # ends after 2
    ("2026-10-21T14:30", "2026-10-21T15:00"),
    ("2026-10-21T15:00:00Z", "2026-10-21T19:30:00Z"),  # UTC that is 11:00-15:30 ET
    ("2026-10-21T13:00", "2026-10-22T11:00"),  # crosses days
    ("2026-10-21T11:00", "2026-10-21T10:00"),  # end before start
])
def test_business_outside_window_refused(env, start, end):
    _, common, _, gcal, *_ = env
    with pytest.raises(common.PolicyError):
        gcal.check_window(start, end)
    with pytest.raises(common.PolicyError):  # unknown/missing category is business, never a bypass
        gcal.check_window(start, end, category="family-ish", critical="yes")


def test_critical_and_personal_bypass(env):
    _, _, _, gcal, *_ = env
    gcal.check_window("2026-10-19T08:00", "2026-10-19T09:00", critical=True)
    gcal.check_window("2026-10-19T08:00", "2026-10-19T09:00", critical="true")
    gcal.check_window("2026-10-24T19:00", "2026-10-24T21:30", category="personal")


# --- Calendar tool --------------------------------------------------------------------------------
def test_create_event_goes_to_own_calendar_with_meet(env):
    auth, common, _, gcal, _, _, calls, _ = env
    connect(auth, common, "own")
    r = gcal.create_event({"title": "Sync", "start": "2026-10-21T10:00", "end": "2026-10-21T10:30",
                           "attendees": ["rick@finverified.ai", "sol@finverified.ai"], "description": "Agenda."})
    assert r["created"] and r["meet_link"] and r["calendar"] == "carly@finverified.ai"
    c = [c for c in calls if "/calendars/primary/events" in c["url"]][-1]
    assert c["auth"] == "Bearer tok_own" and "conferenceDataVersion=1" in c["url"]
    assert c["body"]["conferenceData"]["createRequest"]["conferenceSolutionKey"]["type"] == "hangoutsMeet"
    assert [a["email"] for a in c["body"]["attendees"]] == ["rick@finverified.ai", "sol@finverified.ai"]
    assert c["body"]["start"]["timeZone"] == "America/New_York"


def test_create_event_enforces_window_and_outside_attendee_approval(env):
    auth, common, _, gcal, approvals, *_ = env
    connect(auth, common, "own")
    ev = {"title": "Opus", "start": "2026-10-21T11:00", "end": "2026-10-21T11:30", "attendees": ["carolina@opus.example"]}
    with pytest.raises(common.PolicyError):
        gcal.create_event({**ev, "start": "2026-10-19T11:00", "end": "2026-10-19T11:30", "attendees": []})
    with pytest.raises(common.PolicyError):  # invite is an email: outside attendee needs a token
        gcal.create_event(ev)
    tok = gcal.propose_event(ev)["approval_token"]
    approve(approvals, tok)
    assert gcal.create_event(ev, tok)["created"]
    with pytest.raises(common.PolicyError):
        gcal.create_event(ev, tok)


def test_free_busy_reads_rick_with_rick_token_only(env):
    auth, common, _, gcal, _, _, calls, _ = env
    connect(auth, common, "rick")
    r = gcal.free_busy("2026-10-21", "2026-10-22")
    assert r["busy"] == [{"start": "2026-10-21T14:00:00Z", "end": "2026-10-21T15:00:00Z"}]
    assert "title" not in json.dumps(r)
    c = [c for c in calls if c["url"].endswith("/freeBusy")][-1]
    assert c["auth"] == "Bearer tok_rick" and c["body"]["items"] == [{"id": "primary"}]


def test_rick_connection_cannot_write_and_tools_wired(env):
    auth, common, mailbox, gcal, _, tools, calls, _ = env
    connect(auth, common, "rick")  # only Rick's read-only token exists
    r = json.loads(tools.h_email({"action": "send", "to": "sol@finverified.ai", "subject": "s", "body": "b"}))
    assert r["success"] is False and "google-own-connect" in r["error"]
    assert not [c for c in calls if c["auth"] == "Bearer tok_rick" and c["method"] == "POST" and "send" in c["url"]]
    names = [t[0] for t in tools.TOOLS]
    assert names == ["carly_gmail", "carly_calendar", "carly_email"]
    for a in ("forward", "attach", "delete", "trash"):
        assert not json.loads(tools.h_email({"action": a}))["success"]
