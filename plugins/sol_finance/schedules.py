"""Reconcile Sol's schedules to deploy/sol/cron/jobs.yaml (idempotent, by name). No hourly heartbeat.

Cron expressions are evaluated in the Hermes configured timezone (``timezone`` in
deploy/sol/config.yaml, America/New_York), not the server's local time.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# deploy/sol/cron/jobs.yaml is the complete list of Sol's jobs. Anything else in the
# live store (including retired jobs) is deleted on reconcile.
SPEC_PATH = Path(__file__).resolve().parents[2] / "deploy" / "sol" / "cron" / "jobs.yaml"


def _load_jobs() -> list:
    from cron import reconcile

    return reconcile.load_spec(SPEC_PATH)


JOBS = _load_jobs()


def ensure_jobs() -> None:
    from cron import reconcile

    result = reconcile.reconcile(JOBS)
    logger.info("sol cron reconciled: %s", result)
