"""Casey v1: own-mailbox connection, allowlist (team + Attio contacts + reply-to-sender), approval tokens,
CAN-SPAM footer, suppression, proactive limits, supervised mode, calendar window.

Network is faked by patching common.http_json. There is only one Google connection (Casey's own).
"""

import base64
import email
import email.policy
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

APPROVER = "U_APPROVER"
TEAM = "team@finverified.example"
_NY = ZoneInfo("America/New_York")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("CASEY_OWN_ACCOUNT", raising=False)
    monkeypatch.setenv("CASEY_SEND_ALLOWLIST", TEAM)
    monkeypatch.delenv("CASEY_SUPERVISED_UNTIL", raising=False)
    monkeypatch.setenv("CASEY_APPROVER_USER_IDS", APPROVER)
    monkeypatch.setenv("CASEY_PUBLIC_URL", "https://casey.example.app")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "cs")
    monkeypatch.setenv("ATTIO_API_KEY", "attio-key")
    from plugins.casey_google import approvals, auth, common, contacts, gcal, mailbox, tools

    calls = []
    attio_people = {"partner@dentalgroup.example": "Pathway Partner", "nobody@random.example": ""}

    def fake(method, url, *, headers=None, body=None, form=None, timeout=30):
        calls.append({"method": method, "url": url, "body": body})
        if url.endswith("/token"):
            if form.get("grant_type") == "authorization_code":
                return {"access_token": "tok_own", "refresh_token": "r_own",
                        "scope": " ".join(auth.OWN_SCOPES), "expires_in": 3600}
            return {"access_token": "tok_own", "expires_in": 3600}
        if url.endswith("/profile"):
            return {"emailAddress": "casey@finverified.ai"}
        if url.endswith("/messages/send"):
            return {"id": "sent1"}
        if url.endswith("/drafts"):
            return {"id": "draft1"}
        if "/calendars/primary/events" in url and method == "POST":
            return {"id": "ev1", "htmlLink": "https://cal/ev1", "hangoutLink": "https://meet.google.com/abc"}
        if url.endswith("/objects/people/records/query"):
            addr = body["filter"]["email_addresses"]["email_address"]["$eq"]
            if addr not in attio_people:
                return {"data": []}
            role = attio_people[addr]
            vals = {"name": [{"full_name": "Dana Partner"}]}
            if role:
                vals["fv_role"] = [{"option": {"title": role}}]
            return {"data": [{"id": {"record_id": "rec-1"}, "values": vals}]}
        if "/messages/" in url and "format=metadata" in url:
            return {"threadId": "t1", "payload": {"headers": [
                {"name": "From", "value": "Dr. Patel <office@patelsmiles.example>"},
                {"name": "Subject", "value": "Question about onboarding"},
                {"name": "Message-ID", "value": "<abc@patelsmiles.example>"}]}}
        raise AssertionError(url)

    monkeypatch.setattr(common, "http_json", fake)
    auth.OWN.cache.clear()
    contacts.clear_cache()
    return auth, common, mailbox, gcal, approvals, tools, contacts, calls


def connect(auth, common):
    url = auth.OWN.authorize_url()
    state = common.load_state(auth.OWN.state_file, {})["state"]
    assert "login_hint=casey%40finverified.ai" in url
    assert auth.handle_callback("own", state)
    assert auth.OWN.connected()


def decode(raw):
    return email.message_from_bytes(base64.urlsafe_b64decode(raw), policy=email.policy.default)


def test_connect_requires_expected_account_and_fresh_state(env):
    auth, common, *_ = env
    assert not auth.OWN.connected()
    connect(auth, common)
    assert not auth.handle_callback("own", "stale")  # single-use state


def test_send_to_team_goes_directly_with_footer(env):
    auth, common, mailbox, gcal, approvals, tools, contacts, calls = env
    connect(auth, common)
    out = json.loads(tools.h_email({"action": "send", "to": [TEAM], "subject": "Hi", "body": "Hello"}))
    assert out["success"] and out["sent"] and out["approved_send"] is False
    raw = [c for c in calls if c["url"].endswith("/messages/send")][-1]["body"]["raw"]
    msg = decode(raw)
    assert msg["From"] == "casey@finverified.ai"
    text = msg.get_content()
    assert "Hobe Sound" in text and "unsubscribe" in text.lower()


def test_attio_contact_with_role_is_allowed_without_role_needs_approval(env):
    auth, common, mailbox, *_ = env
    connect(auth, common)
    assert mailbox.off_allowlist(["partner@dentalgroup.example"]) == []
    assert mailbox.off_allowlist(["nobody@random.example"]) == ["nobody@random.example"]
    assert mailbox.off_allowlist(["unknown@nowhere.example"]) == ["unknown@nowhere.example"]
    with pytest.raises(common.PolicyError):
        mailbox.send({"to": ["unknown@nowhere.example"], "subject": "x", "body": "y"})


def test_supervised_mode_makes_attio_contacts_need_approval(env, monkeypatch):
    auth, common, mailbox, *_ = env
    monkeypatch.setenv("CASEY_SUPERVISED_UNTIL", "2999-01-01")
    assert mailbox.supervised()
    assert mailbox.off_allowlist(["partner@dentalgroup.example"]) == ["partner@dentalgroup.example"]
    monkeypatch.setenv("CASEY_SUPERVISED_UNTIL", "2000-01-01")
    assert not mailbox.supervised()
    assert mailbox.off_allowlist(["partner@dentalgroup.example"]) == []


def test_approval_token_single_use_and_identity(env):
    auth, common, mailbox, gcal, approvals, tools, *_ = env
    connect(auth, common)
    draft = {"to": ["unknown@nowhere.example"], "subject": "Hello", "body": "Body"}
    p = mailbox.propose(draft)
    tok = p["approval_token"]
    assert p["recipients_needing_approval"] == ["unknown@nowhere.example"]
    ok, _ = approvals.confirm(tok, "U_SOMEONE_ELSE")
    assert not ok
    ok, _ = approvals.confirm(tok, APPROVER)
    assert ok
    with pytest.raises(common.PolicyError):  # changed after approval
        mailbox.send({**draft, "body": "Edited"}, tok)
    out = mailbox.send(draft, tok)
    assert out["sent"] and out["approved_send"]
    with pytest.raises(common.PolicyError):  # replay
        mailbox.send(draft, tok)


def test_reply_to_original_sender_is_allowed_and_threaded(env):
    auth, common, mailbox, gcal, approvals, tools, contacts, calls = env
    connect(auth, common)
    out = json.loads(tools.h_email({"action": "reply", "message_id": "m1", "body": "Here is the next step."}))
    assert out["success"] and out["reply"] and out["to"] == ["office@patelsmiles.example"]
    sent = [c for c in calls if c["url"].endswith("/messages/send")][-1]["body"]
    assert sent["threadId"] == "t1"
    msg = decode(sent["raw"])
    assert msg["In-Reply-To"] == "<abc@patelsmiles.example>" and msg["Subject"] == "Re: Question about onboarding"


def test_suppression_blocks_send(env):
    auth, common, mailbox, *_ = env
    connect(auth, common)
    mailbox.suppress("partner@dentalgroup.example", "replied unsubscribe")
    with pytest.raises(common.PolicyError):
        mailbox.send({"to": ["partner@dentalgroup.example"], "subject": "x", "body": "y"})


def test_proactive_limits(env):
    auth, common, mailbox, *_ = env
    connect(auth, common)
    day = datetime(2026, 11, 16, 10, 0, tzinfo=_NY)
    night = datetime(2026, 11, 16, 21, 0, tzinfo=_NY)
    mailbox.check_proactive(["partner@dentalgroup.example"], day)
    with pytest.raises(common.PolicyError):
        mailbox.check_proactive(["partner@dentalgroup.example"], night)
    mailbox._record_proactive(["partner@dentalgroup.example"])
    with pytest.raises(common.PolicyError):  # 72-hour cap
        mailbox.check_proactive(["partner@dentalgroup.example"], day)


def test_never_forwards(env):
    auth, common, mailbox, *_ = env
    with pytest.raises(common.PolicyError):
        mailbox.build_draft({"to": [TEAM], "subject": "Fwd: secret", "body": "x"})


def test_calendar_window_and_meet_link(env):
    auth, common, mailbox, gcal, *_ = env
    connect(auth, common)
    with pytest.raises(common.PolicyError):  # Saturday
        gcal.check_window("2026-11-21T10:00:00-05:00", "2026-11-21T10:30:00-05:00")
    with pytest.raises(common.PolicyError):  # too late
        gcal.check_window("2026-11-20T19:45:00-05:00", "2026-11-20T20:15:00-05:00")
    out = gcal.create_event({"title": "Onboarding help", "start": "2026-11-20T14:00:00-05:00",
                             "end": "2026-11-20T14:15:00-05:00", "attendees": ["partner@dentalgroup.example"]})
    assert out["created"] and out["meet_link"].startswith("https://meet.google.com/")
    with pytest.raises(common.PolicyError):  # outsider needs a token
        gcal.create_event({"title": "x", "start": "2026-11-20T14:00:00-05:00", "end": "2026-11-20T14:15:00-05:00",
                           "attendees": ["unknown@nowhere.example"]})


def test_attio_down_fails_closed(env, monkeypatch):
    auth, common, mailbox, gcal, approvals, tools, contacts, calls = env

    def boom(*a, **k):
        raise RuntimeError("attio down")

    monkeypatch.setattr(common, "http_json", boom)
    contacts.clear_cache()
    assert mailbox.off_allowlist(["partner@dentalgroup.example"]) == ["partner@dentalgroup.example"]
