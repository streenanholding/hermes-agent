"""#agent-log lines, bundled DMs to Rick, never the same failure twice."""

import pytest

from gateway import ops_alerts as oa


@pytest.fixture(autouse=True)
def _reset():
    oa.reset_for_tests()


def test_agent_log_is_one_line_and_dedupes_by_key():
    sent = []
    send = lambda t: sent.append(t) or True
    assert oa.post_agent_log("job\nfailed:\n  boom", key="k", _send=send)
    assert oa.post_agent_log("job failed again", key="k", _send=send) is False
    assert sent == ["job failed: boom"]


def test_failed_agent_log_send_releases_key_so_it_can_retry():
    assert oa.post_agent_log("x", key="k", _send=lambda t: False) is False
    assert oa.post_agent_log("x", key="k", _send=lambda t: True) is True


def test_recovery_allows_the_failure_to_post_again(monkeypatch):
    sent = []
    monkeypatch.setattr(oa, "_send_channel", lambda t: sent.append(t) or True)
    job = {"id": "j1", "name": "nightly"}
    oa.log_job_result(job, False, "boom")
    oa.log_job_result(job, False, "boom")  # same failure: silent
    oa.log_job_result(job, True)
    oa.log_job_result(job, False, "boom")  # new failure after success: posts
    assert [s.split(":")[0] for s in sent] == ["⚠️ nightly failed", "✅ nightly ran", "⚠️ nightly failed"]


def test_fewer_than_three_dms_go_individually():
    oa.notify_rick("need A", key="a"), oa.notify_rick("need B", key="b")
    out = []
    assert oa.flush_pending(_send=lambda t: out.append(t) or True) == 2
    assert out == ["need A", "need B"]


def test_three_or_more_dms_are_one_bundle():
    for k in "abc":
        oa.notify_rick(f"need {k}", key=k)
    out = []
    assert oa.flush_pending(_send=lambda t: out.append(t) or True) == 1
    assert len(out) == 1 and "3 items" in out[0] and "need a" in out[0] and "need c" in out[0]


def test_duplicate_dm_key_is_dropped():
    assert oa.notify_rick("key dead", key="auth") is True
    assert oa.notify_rick("key dead", key="auth") is False
    out = []
    oa.flush_pending(_send=lambda t: out.append(t) or True)
    assert out == ["key dead"]


def test_failed_dm_is_requeued_not_lost_or_doubled():
    oa.notify_rick("need A", key="a")
    assert oa.flush_pending(_send=lambda t: False) == 0
    out = []
    assert oa.flush_pending(_send=lambda t: out.append(t) or True) == 1
    assert out == ["need A"]
    assert oa.flush_pending(_send=lambda t: out.append(t) or True) == 0


def test_no_token_means_no_send(monkeypatch):
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    assert oa.post_agent_log("x") is False
