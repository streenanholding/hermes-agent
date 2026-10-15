"""Seed Sol's three schedules (idempotent, by name). No hourly heartbeat.

Cron expressions are evaluated in the Hermes configured timezone (``timezone`` in
deploy/sol/config.yaml, America/New_York), not the server's local time.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Jobs that were replaced by a differently named job. ensure_jobs() removes them.
RETIRED_JOBS = ("sol-weekly-cfo-report",)  # Monday report, replaced by sol-weekly-cfo-report-fri

JOBS = [
    {"name": "sol-weekly-cfo-report-fri", "schedule": "0 7 * * 5", "model": "openrouter/anthropic/claude-sonnet-4.5",
     "prompt": ("Prepare the weekly CFO + controller report using templates/weekly-cfo-report.md for this week. "
                "Pull Xero Reports/ProfitAndLoss, Reports/BalanceSheet, Reports/BankSummary, Reports/AgedPayablesByContact "
                "and Reports/TrialBalance with sol_xero; Mercury with sol_mercury; Stripe with sol_stripe; AWS (cached) with "
                "sol_aws; and sol_budget status. Lead with the bottom line. Include: cash and runway; the week's spend by "
                "vendor; the unreconciled items count; drafts awaiting Rick's approval; a payroll journal vs Mercury check; "
                "and items needing decisions. Check all math and dates before sending. Email the report with sol_email_report "
                "(it goes to Rick and Nancy only). Then DM Rick on Slack with sol_dm_rick: a 3-line summary saying the report "
                "was emailed. Drafts and proposals only; no money movement, no posting, no reconciling.")},
    {"name": "sol-month-end-close", "schedule": "0 7 5 * *", "model": "openrouter/anthropic/claude-sonnet-4.5",
     "prompt": ("Month-end close package (drafts only) plus vendor optimization review for the month just ended, per the "
                "controller-cpa and vendors-billing skills. Save to Drive 'FinVerified Finance' and mention it in the next Friday report.")},
    {"name": "sol-daily-budget-check", "schedule": "30 6 * * *", "no_agent": True, "script": "sol_daily_budget_check.py"},
]


def _remove_retired(cj) -> None:
    """Remove retired jobs by name; fall back to disabling if removal is unsupported or fails."""
    for j in cj.list_jobs(include_disabled=True):
        if j.get("name") not in RETIRED_JOBS:
            continue
        try:
            if cj.remove_job(j["id"]):
                continue
        except Exception:
            logger.exception("could not remove retired job %s", j.get("name"))
        try:
            if j.get("enabled", True):
                cj.update_job(j["id"], {"enabled": False, "state": "paused"})
        except Exception:
            logger.exception("could not disable retired job %s", j.get("name"))


def ensure_jobs() -> None:
    from cron import jobs as cj

    try:
        _remove_retired(cj)
    except Exception:
        logger.exception("retired-job cleanup failed")
    have = {j.get("name") for j in cj.list_jobs(include_disabled=True)}
    for j in JOBS:
        if j["name"] in have:
            continue
        try:
            cj.create_job(prompt=j.get("prompt"), schedule=j["schedule"], name=j["name"], model=j.get("model"),
                          no_agent=j.get("no_agent", False), script=j.get("script"), deliver="local")
        except Exception:
            logger.exception("could not seed %s", j["name"])
