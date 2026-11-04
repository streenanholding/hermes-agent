"""Carol's review gate: nothing goes outside FinVerified until Rick replies SEND to the exact draft.

Network is faked by patching common.http_json.
"""

import base64
import json

import pytest

from carol_google import auth, common, gmail, tools

CAROL = "carol@finverified.ai"
RICK = "rick@finverified.ai"


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("CAROL_EMAIL", CAROL)
    monkeypatch.setenv("CAROL_SEND_DOMAINS", "payer.example")
    monkeypatch.setenv("CAROL_ALWAYS_CC", "rick@finverified.ai,ncoy@finverified.ai")
    monkeypatch.delenv("CAROL_REVIEWERS", raising=False)
    monkeypatch.setattr(common, "carol_config", lambda: {"allow_send": True})
    monkeypatch.setattr(auth, "headers", lambda: {"Authorization": "Bearer at"})


class Fake:
    """A tiny Gmail: one draft, one review thread, configurable replies."""

    def __init__(self, monkeypatch):
        self.raw = "draft-v1"
        self.replies = []  # (from, first_line, internalDate, auth_results, labels)
        self.sent = []
        self.review_sent = []
        monkeypatch.setattr(common, "http_json", self._json)

    def _json(self, method, url, **kw):
        hdrs = [
            {"name": "To", "value": "edi@payer.example"},
            {"name": "Cc", "value": "rick@finverified.ai, ncoy@finverified.ai"},
            {"name": "Subject", "value": "[FV-PAY-TEST] Direct 835 enrollment"},
        ]
        if "drafts/d1?format=raw" in url:
            return {"message": {"raw": _b64(self.raw)}}
        if "drafts/d1?format=metadata" in url:
            return {"message": {"payload": {"headers": hdrs}}}
        if "drafts/d1?format=full" in url:
            return {"message": {"payload": {"headers": hdrs, "mimeType": "text/plain",
                                            "body": {"data": _b64("Hello payer team")}}}}
        if url.endswith("/messages/send"):
            self.review_sent.append(kw["body"]["raw"])
            return {"id": "r1", "threadId": "t1", "internalDate": "1000"}
        if "threads/t1" in url:
            msgs = []
            for frm, line, ts, auth_res, labels in self.replies:
                h = [{"name": "From", "value": frm}]
                if auth_res:
                    h.append({"name": "Authentication-Results", "value": auth_res})
                msgs.append({"internalDate": str(ts), "labelIds": labels,
                             "payload": {"headers": h, "mimeType": "text/plain",
                                         "body": {"data": _b64(line + "\n\n> quoted draft")}}})
            return {"messages": msgs}
        if url.endswith("/drafts/send"):
            self.sent.append(kw["body"]["id"])
            return {"id": "m1", "threadId": "t9"}
        raise AssertionError(f"unexpected call {method} {url}")


def test_outside_email_blocked_without_review(monkeypatch):
    f = Fake(monkeypatch)
    with pytest.raises(common.PolicyError, match="hasn't reviewed"):
        gmail.send_draft("d1")
    assert f.sent == []


def test_review_email_goes_only_to_rick_with_full_draft(monkeypatch):
    f = Fake(monkeypatch)
    out = gmail.request_review("d1")
    assert out["review_sent_to"] == [RICK]
    raw = base64.urlsafe_b64decode(f.review_sent[0]).decode()
    assert "To: rick@finverified.ai" in raw
    assert "[REVIEW d1]" in raw and "Hello payer team" in raw and "edi@payer.example" in raw
    assert f.sent == []


def test_waiting_until_rick_replies(monkeypatch):
    f = Fake(monkeypatch)
    gmail.request_review("d1")
    with pytest.raises(common.PolicyError, match="waiting for Rick"):
        gmail.send_draft("d1")
    assert f.sent == []


def test_sends_after_rick_replies_send_and_only_once(monkeypatch):
    f = Fake(monkeypatch)
    gmail.request_review("d1")
    f.replies.append((f"Rick <{RICK}>", "SEND", 2000, "mx.google.com; dkim=pass; dmarc=pass", []))
    assert gmail.send_draft("d1")["status"] == "sent"
    assert f.sent == ["d1"]
    with pytest.raises(common.PolicyError, match="already sent"):
        gmail.send_draft("d1")


def test_changes_requested_blocks_send(monkeypatch):
    f = Fake(monkeypatch)
    gmail.request_review("d1")
    f.replies.append((RICK, "Change the second paragraph", 2000, "", []))
    with pytest.raises(common.PolicyError, match="not SEND"):
        gmail.send_draft("d1")
    assert f.sent == []


def test_latest_reply_wins(monkeypatch):
    f = Fake(monkeypatch)
    gmail.request_review("d1")
    f.replies += [(RICK, "SEND", 2000, "", []), (RICK, "NO, hold this", 3000, "", [])]
    with pytest.raises(common.PolicyError, match="not SEND"):
        gmail.send_draft("d1")


def test_edited_draft_needs_new_review(monkeypatch):
    f = Fake(monkeypatch)
    gmail.request_review("d1")
    f.replies.append((RICK, "SEND", 2000, "", []))
    f.raw = "draft-v2"
    with pytest.raises(common.PolicyError, match="changed after Rick reviewed"):
        gmail.send_draft("d1")
    assert f.sent == []


@pytest.mark.parametrize("frm,auth_res,labels", [
    ("someone@payer.example", "", []),           # not a reviewer
    (RICK, "mx.google.com; dmarc=fail", []),      # spoofed
    (RICK, "", ["SPAM"]),                         # in spam
])
def test_untrusted_send_replies_ignored(monkeypatch, frm, auth_res, labels):
    f = Fake(monkeypatch)
    gmail.request_review("d1")
    f.replies.append((frm, "SEND", 2000, auth_res, labels))
    with pytest.raises(common.PolicyError, match="waiting for Rick"):
        gmail.send_draft("d1")
    assert f.sent == []


def test_reply_older_than_request_ignored(monkeypatch):
    f = Fake(monkeypatch)
    gmail.request_review("d1")
    f.replies.append((RICK, "SEND", 500, "", []))
    with pytest.raises(common.PolicyError, match="waiting for Rick"):
        gmail.send_draft("d1")


def test_reviewers_must_be_finverified(monkeypatch):
    Fake(monkeypatch)
    monkeypatch.setenv("CAROL_REVIEWERS", "rick@gmail.com")
    with pytest.raises(common.PolicyError, match="finverified.ai"):
        gmail.request_review("d1")


def test_sending_still_off_unless_enabled(monkeypatch):
    f = Fake(monkeypatch)
    monkeypatch.setattr(common, "carol_config", lambda: {})
    with pytest.raises(common.PolicyError, match="Sending is off"):
        gmail.send_draft("d1")
    assert f.sent == []


def test_tool_exposes_request_review(monkeypatch):
    Fake(monkeypatch)
    out = json.loads(tools.h_gmail({"action": "request_review", "draft_id": "d1"}))
    assert out["success"] and out["review_sent_to"] == [RICK]
