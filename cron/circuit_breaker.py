"""Cron failure circuit breaker.

A recurring job that fails ``cron.circuit_breaker_threshold`` runs in a row
(default 3, ``0`` disables) is paused automatically and ONE alert goes to the
``#agent-log`` (one line, deduped per pause). While it stays paused it never
runs, so it cannot post per-run failures. ``digest_line`` lists paused jobs for
the weekly report; nothing re-posts them daily.

``failure_streak`` is maintained by ``cron.jobs.mark_job_run`` (reset on any
success, delivery-only failures don't count). ``resume_job`` clears the
``paused_by`` marker and the streak so a resumed job gets a fresh count.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 3
PAUSED_BY = "circuit_breaker"


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
        f"Last error: {why} "
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
        from gateway.ops_alerts import post_agent_log

        post_agent_log(
            pause_message(job, streak, error or job.get("last_error")),
            key=f"breaker:{job_id}:{updated.get('paused_at')}",
        )
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
