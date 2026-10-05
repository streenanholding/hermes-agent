"""Seed Sol's three schedules (idempotent, by name). No hourly heartbeat."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

JOBS = [
    {"name": "sol-weekly-cfo-report", "schedule": "0 7 * * 1", "model": "openrouter/anthropic/claude-sonnet-4.5",
     "prompt": ("Prepare the weekly CFO report from templates/weekly-cfo-report.md for this week. Pull data with sol_mercury, "
               "sol_stripe, sol_aws (cached) and sol_budget status; include the monthly AI spend line. Lead with the bottom line. "
               "Send it to Rick with sol_dm_rick. Drafts and proposals only; no money movement.")},
    {"name": "sol-month-end-close", "schedule": "0 7 5 * *", "model": "openrouter/anthropic/claude-sonnet-4.5",
     "prompt": ("Month-end close package (drafts only) plus vendor optimization review for the month just ended, per the "
               "controller-cpa and vendors-billing skills. Save to Drive 'FinVerified Finance' and mention it in the next Monday report.")},
    {"name": "sol-daily-budget-check", "schedule": "30 6 * * *", "no_agent": True, "script": "sol_daily_budget_check.py"},
]


def ensure_jobs() -> None:
    from cron import jobs as cj

    have = {j.get("name") for j in cj.list_jobs(include_disabled=True)}
    for j in JOBS:
        if j["name"] in have:
            continue
        try:
            cj.create_job(prompt=j.get("prompt"), schedule=j["schedule"], name=j["name"], model=j.get("model"),
                          no_agent=j.get("no_agent", False), script=j.get("script"), deliver="local")
        except Exception:
            logger.exception("could not seed %s", j["name"])
