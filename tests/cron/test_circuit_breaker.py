"""Cron failure circuit breaker: 3 consecutive failures auto-pause with ONE alert.

Contract:
- Failures below the threshold keep the job scheduled and send no breaker alert.
- The Nth consecutive failure pauses the job and posts exactly one alert; the
  normal per-run failure post for that run is suppressed.
- A success resets the streak.
- A paused job produces no further failure posts or alerts.
- The daily digest lists self-paused jobs (once per day) until they're resumed.
- resume_job clears the marker and the streak.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

import cron.circuit_breaker as cb
from cron.jobs import create_job, get_job, mark_job_run, pause_job, resume_job


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr("cron.jobs.CRON_DIR", tmp_path / "cron")
    monkeypatch.setattr("cron.jobs.JOBS_FILE", tmp_path / "cron" / "jobs.json")
    monkeypatch.setattr("cron.jobs.OUTPUT_DIR", tmp_path / "cron" / "output")
    monkeypatch.setattr(cb, "threshold", lambda: 3)
    return tmp_path


@pytest.fixture()
def alerts():
    sent = []
    with patch("gateway.ops_alerts.post_slack_alert", side_effect=lambda t, **k: sent.append(t) or True):
        yield sent


def _fail(job_id, err="boom"):
    """Mirror the scheduler: record the failed run, then let the breaker act."""
    assert mark_job_run(job_id, False, err)
    return cb.trip_if_needed(job_id, err)


def _job():
    return create_job(prompt="p", schedule="every 5m", name="flaky")


def test_pauses_on_third_consecutive_failure_with_one_alert(store, alerts):
    jid = _job()["id"]
    assert not _fail(jid) and not _fail(jid)
    assert alerts == [] and get_job(jid)["state"] == "scheduled"

    assert _fail(jid) is True
    job = get_job(jid)
    assert job["state"] == "paused" and job["enabled"] is False
    assert job["paused_by"] == cb.PAUSED_BY
    assert len(alerts) == 1
    assert "flaky" in alerts[0] and "3 failed runs" in alerts[0] and "boom" in alerts[0]


def test_success_resets_streak(store, alerts):
    jid = _job()["id"]
    _fail(jid), _fail(jid)
    assert mark_job_run(jid, True)
    _fail(jid), _fail(jid)
    assert get_job(jid)["state"] == "scheduled" and alerts == []


def test_no_further_alerts_while_paused(store, alerts):
    jid = _job()["id"]
    for _ in range(3):
        _fail(jid)
    assert len(alerts) == 1
    # a stray extra failure (e.g. manual run) neither re-alerts nor re-pauses
    assert _fail(jid) is False
    assert len(alerts) == 1
    assert cb.suppress_failure_post(get_job(jid)) is True


def test_third_failure_replaces_normal_failure_post(store):
    jid = _job()["id"]
    _fail(jid), _fail(jid)
    job = get_job(jid)
    assert cb.would_trip(job) is True  # next failure trips...
    assert cb.suppress_failure_post(job) is True  # ...so its normal post is replaced
    # earlier failures still post normally
    fresh = create_job(prompt="p", schedule="every 5m", name="other")
    assert cb.suppress_failure_post(fresh) is False


def test_threshold_zero_disables(store, monkeypatch, alerts):
    monkeypatch.setattr(cb, "threshold", lambda: 0)
    jid = _job()["id"]
    for _ in range(5):
        assert _fail(jid) is False
    assert get_job(jid)["state"] == "scheduled" and alerts == []


def test_manual_pause_is_not_self_paused(store, alerts):
    jid = _job()["id"]
    pause_job(jid, "me")
    assert cb.self_paused_jobs() == []
    assert cb.digest_line() == ""


def test_digest_lists_self_paused_once_per_day_until_resumed(store, alerts):
    jid = _job()["id"]
    for _ in range(3):
        _fail(jid)
    alerts.clear()
    day1 = datetime(2026, 10, 21, 9, tzinfo=timezone.utc)

    assert cb.maybe_post_daily_digest(day1) is True
    assert len(alerts) == 1 and "flaky" in alerts[0]
    assert cb.maybe_post_daily_digest(day1.replace(hour=15)) is False  # same day
    assert cb.maybe_post_daily_digest(day1.replace(day=22)) is True  # next day

    resume_job(jid)
    job = get_job(jid)
    assert job["state"] == "scheduled" and not job.get("paused_by")
    assert job["failure_streak"] == 0
    assert cb.maybe_post_daily_digest(day1.replace(day=23)) is False  # nothing to list


def test_one_shot_jobs_never_trip(store, alerts):
    jid = create_job(prompt="p", schedule="30m", name="once")["id"]
    for _ in range(4):
        assert _fail(jid) is False
    assert alerts == []
