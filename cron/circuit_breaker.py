"""Cron failure circuit breaker.

A recurring job that fails ``cron.circuit_breaker_threshold`` runs in a row
(default 3, ``0`` disables) is paused automatically and ONE alert goes to the
operator (owner DM + alert channel). While it stays paused it never runs, so
it cannot post per-run failures; a daily digest line keeps listing it until
someone resumes it.

``failure_streak`` is maintained by ``cron.jobs.mark_job_run`` (reset on any
success, delivery-only failures don't count). ``resume_job`` clears the
``paused_by`` marker and the streak so a resumed job gets a fresh count.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 3
PAUSED_BY = "circuit_breaker"
_DIGEST_MARKER = ".breaker_digest_date"


def threshold() -> int:
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        return int((cfg.get("cron") or {}).get("circuit_breaker_threshold", DEFAULT_THRESHOLD))
    except Exception:
        return DEFAULT_THRESHOLD


def _is_recurring(job: Dict[str, Any]) -> bool:
    return (job.get("schedule") or {}).get("kind") in {"cron", "interval"}


def is_self_paused(job: Dict[str, Any]) -> bool:
    return job.get("paused_by") == PAUSED_BY and job.get("state") == "paused"


def would_trip(job: Dict[str, Any]) -> bool:
    """True if the run that is about to be recorded as failed trips the breaker.

    Used BEFORE ``mark_job_run`` (stored streak + this run) so the normal
    per-run failure post can be replaced by the single pause alert.
    """
    limit = threshold()
    if limit <= 0 or not _is_recurring(job) or is_self_paused(job):
        return False
    return int(job.get("failure_streak") or 0) + 1 >= limit


def suppress_failure_post(job: Dict[str, Any]) -> bool:
    """True when this failure must not produce a normal per-run post."""
    return is_self_paused(job) or would_trip(job)


def pause_message(job: Dict[str, Any], streak: int, error: Optional[str]) -> str:
    name = job.get("name") or job.get("id") or "cron job"
    why = " ".join(str(error or "unknown error").split())[:300]
    return (
        f"⏸️ Cron job '{name}' paused itself after {streak} failed runs in a row.\n"
        f"Last error: {why}\n"
        "No more failure posts will be sent for it. It stays paused until "
        f"resumed: `hermes cron resume {job.get('id')}`."
    )


def trip_if_needed(job_id: str, error: Optional[str]) -> bool:
    """Call after ``mark_job_run(job_id, False, ...)``. Pause + alert once.

    Returns True only on the call that paused the job.
    """
    from cron.jobs import get_job, update_job, _hermes_now

    limit = threshold()
    if limit <= 0:
        return False
    job = get_job(job_id)
    if not job or not _is_recurring(job) or job.get("state") == "paused":
        return False
    streak = int(job.get("failure_streak") or 0)
    if streak < limit:
        return False
    updated = update_job(
        job_id,
        {
            "enabled": False,
            "state": "paused",
            "paused_at": _hermes_now().isoformat(),
            "paused_reason": f"circuit breaker: {streak} consecutive failures",
            "paused_by": PAUSED_BY,
        },
    )
    if not updated:
        return False
    try:
        from gateway.ops_alerts import post_slack_alert

        post_slack_alert(pause_message(job, streak, error or job.get("last_error")))
    except Exception:
        logger.warning("circuit breaker alert failed for job %s", job_id, exc_info=True)
    return True


def self_paused_jobs() -> List[Dict[str, Any]]:
    from cron.jobs import list_jobs

    return [j for j in list_jobs(include_disabled=True) if is_self_paused(j)]


def digest_line() -> str:
    """One line listing self-paused jobs, or "" when there are none."""
    jobs = self_paused_jobs()
    if not jobs:
        return ""
    names = ", ".join(
        f"{j.get('name') or j.get('id')} (paused {str(j.get('paused_at') or '?')[:10]})"
        for j in jobs
    )
    return f"⏸️ Self-paused cron jobs awaiting resume: {names}"


def maybe_post_daily_digest(now: Optional[datetime] = None) -> bool:
    """Post the digest line at most once per calendar day. Called from tick()."""
    from cron.jobs import _current_cron_store, _hermes_now

    now = now or _hermes_now()
    marker = _current_cron_store().cron_dir / _DIGEST_MARKER
    today = now.date().isoformat()
    try:
        if marker.exists() and marker.read_text().strip() == today:
            return False
    except OSError:
        pass
    line = digest_line()
    try:
        marker.write_text(today)
    except OSError:
        logger.debug("could not write breaker digest marker", exc_info=True)
    if not line:
        return False
    from gateway.ops_alerts import post_slack_alert

    return post_slack_alert(line)
