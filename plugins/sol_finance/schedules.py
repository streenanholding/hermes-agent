"""Seed Sol's three schedules (idempotent, by name). No hourly heartbeat."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Jobs that were replaced and must no longer run.
RETIRED_JOBS: List[str] = ["sol-weekly-cfo-report"]

JOBS: List[Dict[str, Any]] = [
    {"name": "sol-weekly-cfo-report-fri", "schedule": "0 7 * * 5", "timezone": "America/New_York",
     "model": "openrouter/anthropic/claude-sonnet-4.5",
     "prompt": ("Prepare the weekly CFO + controller report from templates/weekly-cfo-report.md for this week. "
                "Pull data with sol_xero (Reports/ProfitAndLoss, Reports/BalanceSheet, Reports/BankSummary, "
                "Reports/AgedPayablesByContact, Reports/TrialBalance), sol_mercury, sol_stripe, sol_aws (use cache) "
                "and sol_budget status. The report must: lead with the bottom line; include cash and runway; "
                "show the week's spend by vendor; give the unreconciled items count; list drafts awaiting Rick's approval; "
                "include a payroll journal vs Mercury check; and end with decisions needed. "
                "Check all math and dates before sending. "
                "Then email the report with sol_email_report to rick@finverified.ai and ncoy@finverified.ai, "
                "then DM Rick in Slack with sol_dm_rick a 3-line summary stating that the report was emailed. "
                "Drafts and proposals only; no money movement.")},
    {"name": "sol-month-end-close", "schedule": "0 7 5 * *", "model": "openrouter/anthropic/claude-sonnet-4.5",
     "prompt": ("Month-end close package (drafts only) plus vendor optimization review for the month just ended, per the "
               "controller-cpa and vendors-billing skills. Save to Drive 'FinVerified Finance' and mention it in the next Friday report.")},
    {"name": "sol-daily-budget-check", "schedule": "30 6 * * *", "no_agent": True, "script": "sol_daily_budget_check.py"},
]


def ensure_jobs() -> None:
    from cron import jobs as cj

    existing = cj.list_jobs(include_disabled=True)
    for j in existing:
        if j.get("name") in RETIRED_JOBS:
            try:
                cj.remove_job(j["id"])
            except Exception:
                logger.exception("could not remove retired job %s", j.get("name"))
    have = {j.get("name") for j in existing}
    for j in JOBS:
        if j["name"] in have:
            continue
        try:
            cj.create_job(prompt=j.get("prompt"), schedule=j["schedule"], name=j["name"], model=j.get("model"),
                          no_agent=j.get("no_agent", False), script=j.get("script"), deliver="local",
                          timezone=j.get("timezone"))
        except Exception:
            logger.exception("could not seed %s", j["name"])
