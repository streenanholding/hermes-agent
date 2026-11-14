"""Carol Gmail send policy: allowlist vs open send_mode (Doctrine v1.2), CC and cap invariants."""

import pytest


@pytest.fixture
def carol(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("CAROL_EMAIL", "carol@finverified.ai")
    monkeypatch.setenv("CAROL_ALWAYS_CC", "rick@finverified.ai")
    monkeypatch.setenv("CAROL_SEND_DOMAINS", "stedi.com")
    monkeypatch.setenv("CAROL_BLOCKED_DOMAINS", "competitor.example")
    from plugins.carol_google import auth, common, gmail

    cfg = {"allow_send": True, "daily_send_cap": 40}
    monkeypatch.setattr(common, "carol_config", lambda: cfg)
    monkeypatch.setattr(auth, "headers", lambda: {})
    draft = {"to": "", "cc": "rick@finverified.ai"}
    sent = []

    def fake(method, url, *, headers=None, body=None, form=None, timeout=30):
        if "drafts/" in url and "format=metadata" in url:
            return {"message": {"payload": {"headers": [
                {"name": "To", "value": draft["to"]}, {"name": "Cc", "value": draft["cc"]}]}}}
        if url.endswith("/drafts/send"):
            sent.append(body["id"])
            return {"id": "m1", "threadId": "t1"}
        raise AssertionError(url)

    monkeypatch.setattr(common, "http_json", fake)
    return gmail, common, cfg, draft, sent


def test_allowlist_blocks_unknown_domain(carol):
    gmail, common, cfg, draft, sent = carol
    draft["to"] = "edi@deltadental.example"
    with pytest.raises(common.PolicyError, match="approved domains"):
        gmail.send_draft("d1")
    assert sent == []


def test_allowlist_allows_listed_domain(carol):
    gmail, common, cfg, draft, sent = carol
    draft["to"] = "partners@stedi.com"
    assert gmail.send_draft("d1")["status"] == "sent"
    assert sent == ["d1"]


def test_open_mode_reaches_any_payer_domain(carol):
    gmail, common, cfg, draft, sent = carol
    cfg["send_mode"] = "open"
    draft["to"] = "edi.enrollment@deltadental.example"
    assert gmail.send_draft("d1")["status"] == "sent"


def test_open_mode_still_blocks_blocklist(carol):
    gmail, common, cfg, draft, sent = carol
    cfg["send_mode"] = "open"
    draft["to"] = "anyone@competitor.example"
    with pytest.raises(common.PolicyError, match="blocked domain"):
        gmail.send_draft("d1")
    assert sent == []


@pytest.mark.parametrize("local", ["press", "media", "newsroom", "support", "info"])
def test_open_mode_never_emails_press_or_support(carol, local):
    gmail, common, cfg, draft, sent = carol
    cfg["send_mode"] = "open"
    draft["to"] = f"{local}@bigpayer.example"
    with pytest.raises(common.PolicyError, match="press, media or support"):
        gmail.send_draft("d1")
    assert sent == []


def test_open_mode_still_requires_cc_on_external(carol):
    gmail, common, cfg, draft, sent = carol
    cfg["send_mode"] = "open"
    draft["to"] = "edi@bigpayer.example"
    draft["cc"] = ""
    with pytest.raises(common.PolicyError, match="must copy"):
        gmail.send_draft("d1")


def test_open_mode_still_respects_daily_cap(carol):
    gmail, common, cfg, draft, sent = carol
    cfg["send_mode"] = "open"
    cfg["daily_send_cap"] = 1
    draft["to"] = "edi@bigpayer.example"
    gmail.send_draft("d1")
    with pytest.raises(common.PolicyError, match="Daily send cap"):
        gmail.send_draft("d2")
    assert sent == ["d1"]


def test_allow_send_off_blocks_everything(carol):
    gmail, common, cfg, draft, sent = carol
    cfg["allow_send"] = False
    cfg["send_mode"] = "open"
    draft["to"] = "edi@bigpayer.example"
    with pytest.raises(common.PolicyError, match="Sending is off"):
        gmail.send_draft("d1")
