"""Cron circuit breaker: self-pause after 3 consecutive failures, post once."""

import pytest

from cron import circuit_breaker as cb
from cron import jobs
from gateway import ops_alerts


@pytest.fixture(autouse=True)
def sent(monkeypatch):
    ops_alerts.reset_for_tests()
    out = []
    monkeypatch.setattr(ops_alerts, "_send_channel", lambda text: out.append(text) or True)
    return out


def _job(schedule="every 5m"):
    return jobs.create_job(prompt="p", schedule=schedule, name="flaky", deliver="local")


def _fail(job_id, error="boom"):
    assert jobs.mark_job_run(job_id, False, error)
    return cb.trip_if_needed(job_id, error)


def test_two_failures_do_not_pause(sent):
    j = _job()
    assert _fail(j["id"]) is False and _fail(j["id"]) is False
    assert jobs.get_job(j["id"])["state"] != "paused"
    assert sent == []


def test_third_failure_pauses_and_posts_once(sent):
    j = _job()
    _fail(j["id"]), _fail(j["id"])
    assert _fail(j["id"]) is True
    paused = jobs.get_job(j["id"])
    assert paused["state"] == "paused" and paused["paused_by"] == cb.PAUSED_BY and paused["enabled"] is False
    assert len(sent) == 1 and "flaky" in sent[0] and "paused itself" in sent[0]
    # a stray 4th call (already paused) neither re-pauses nor re-posts
    assert cb.trip_if_needed(j["id"], "boom") is False
    assert len(sent) == 1


def test_success_resets_streak(sent):
    j = _job()
    _fail(j["id"]), _fail(j["id"])
    jobs.mark_job_run(j["id"], True)
    _fail(j["id"]), _fail(j["id"])
    assert jobs.get_job(j["id"])["state"] != "paused"
    assert sent == []


def test_would_trip_suppresses_the_normal_failure_post():
    j = _job()
    _fail(j["id"]), _fail(j["id"])
    live = jobs.get_job(j["id"])
    assert cb.would_trip(live) is True and cb.suppress_failure_post(live) is True


def test_resume_gives_a_fresh_count(sent):
    j = _job()
    for _ in range(3):
        _fail(j["id"])
    jobs.resume_job(j["id"])
    resumed = jobs.get_job(j["id"])
    assert resumed["failure_streak"] == 0 and resumed.get("paused_by") is None
    assert _fail(j["id"]) is False  # one failure after resume does not re-trip


def test_one_shot_jobs_are_never_self_paused():
    j = jobs.create_job(prompt="p", schedule="30m", name="once", deliver="local")
    for _ in range(4):
        jobs.mark_job_run(j["id"], False, "boom")
    assert cb.trip_if_needed(j["id"], "boom") is False


def test_threshold_zero_disables(monkeypatch):
    monkeypatch.setattr(cb, "threshold", lambda: 0)
    j = _job()
    for _ in range(5):
        assert _fail(j["id"]) is False


def test_digest_line_lists_only_self_paused():
    j = _job()
    for _ in range(3):
        _fail(j["id"])
    other = jobs.create_job(prompt="p", schedule="every 5m", name="fine", deliver="local")
    line = cb.digest_line()
    assert "flaky" in line and "fine" not in line and other["id"]
