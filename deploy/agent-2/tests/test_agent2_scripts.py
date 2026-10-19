# SYNTHETIC_TEST_DATA — every identifier below is fake, used to prove the
# draft check rejects PHI/bank patterns. PHI-SCANNER-ACKNOWLEDGED: SYNTHETIC_TEST_DATA
"""Tests for Agent 2's no_agent cron scripts. Synthetic data only.

Run: python -m pytest deploy/agent-2/tests -q
Each script runs as a subprocess against a temp HERMES_HOME, the way Hermes
cron runs it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    for d in ("trackers/vendors", "trackers/practices", "drafts/pending", "state", "logs/opus", "quality"):
        (tmp_path / d).mkdir(parents=True)
    shutil.copytree(ROOT / "templates", tmp_path / "templates")
    shutil.copy(ROOT / "quality" / "prohibited-claims.txt", tmp_path / "quality" / "prohibited-claims.txt")
    return tmp_path


def run(script: str, home: Path, **env) -> subprocess.CompletedProcess:
    full = {k: v for k, v in os.environ.items() if not k.startswith("AGENT2_")}
    full.update({"AGENT2_DATA_DIR": str(home), **env})
    return subprocess.run([sys.executable, str(SCRIPTS / script)], env=full,
                          capture_output=True, text=True, timeout=30)


def tracker(home: Path, kind: str, slug: str, last: str, status: str = "IN MOTION") -> None:
    (home / "trackers" / kind / f"{slug}.md").write_text(
        f"# {slug}\n\n- **Status:** {status}\n- **Owner:** Rick\n"
        f"- **Last movement:** {last}\n- **Next action:** chase reply (Rick)\n"
    )


# ── budget guard ───────────────────────────────────────────────────────────

def budget(home: Path) -> dict:
    return json.loads((home / "state" / "budget.json").read_text())


def test_budget_ok_is_silent(home):
    r = run("budget_guard.py", home, AGENT2_BUDGET_SIMULATE_SPEND_PCT="40")
    assert r.returncode == 0 and r.stdout == ""
    assert budget(home)["state"] == "ok"


def test_budget_warns_once_at_80(home):
    r = run("budget_guard.py", home, AGENT2_BUDGET_SIMULATE_SPEND_PCT="80", AGENT2_RICK_SLACK_ID="U000TEST")
    assert "<@U000TEST>" in r.stdout and "80%" in r.stdout and "paused" in r.stdout
    assert budget(home)["state"] == "warn"
    again = run("budget_guard.py", home, AGENT2_BUDGET_SIMULATE_SPEND_PCT="85")
    assert again.stdout == ""  # no repeat alert while still in warn


def test_budget_stops_at_100(home):
    run("budget_guard.py", home, AGENT2_BUDGET_SIMULATE_SPEND_PCT="90")
    r = run("budget_guard.py", home, AGENT2_BUDGET_SIMULATE_SPEND_PCT="100")
    assert "budget cap" in r.stdout
    assert budget(home)["state"] == "stop"


def test_budget_recovers_after_reset(home):
    run("budget_guard.py", home, AGENT2_BUDGET_SIMULATE_SPEND_PCT="100")
    r = run("budget_guard.py", home, AGENT2_BUDGET_SIMULATE_SPEND_PCT="2")
    assert "back under 80%" in r.stdout and budget(home)["state"] == "ok"


def test_budget_missing_env_fails_without_leaking(home):
    r = run("budget_guard.py", home)
    assert r.returncode == 1 and "AGENT2_LITELLM_BASE_URL" in r.stdout
    assert not (home / "state" / "budget.json").exists()


def test_spend_is_logged_without_secrets(home):
    run("budget_guard.py", home, AGENT2_BUDGET_SIMULATE_SPEND_PCT="10", AGENT2_LITELLM_KEY="sk-should-not-appear")
    log = (home / "logs" / "spend.jsonl").read_text()
    row = json.loads(log.splitlines()[-1])
    assert row["job"] == "budget_guard" and row["service"] == "hermes-agent-2"
    assert "sk-should-not-appear" not in log


# ── stale check ────────────────────────────────────────────────────────────

def test_stale_flags_at_5_and_escalates_at_10(home):
    # 2026-09-30 is a Wednesday.
    tracker(home, "vendors", "fresh-clearinghouse", "2026-09-28")
    tracker(home, "vendors", "synthetic-stedi", "2026-09-23")      # 5 business days
    tracker(home, "practices", "test-family-dental", "2026-09-16")  # 10 business days
    tracker(home, "vendors", "done-vendor", "2026-01-01", status="LIVE")
    r = run("stale_check.py", home, AGENT2_TODAY="2026-09-30", AGENT2_RICK_SLACK_ID="U000TEST")
    out = r.stdout
    assert "fresh-clearinghouse" not in out and "done-vendor" not in out
    flagged, escalated = out.split("Flagged")[1], out.split("Flagged")[0]
    assert "synthetic-stedi" in flagged
    assert "<@U000TEST>" in escalated and "test-family-dental" in escalated


def test_stale_silent_when_nothing_stale(home):
    tracker(home, "vendors", "fresh", "2026-09-29")
    assert run("stale_check.py", home, AGENT2_TODAY="2026-09-30").stdout == ""


def test_stale_reports_unreadable_tracker(home):
    (home / "trackers" / "vendors" / "no-date.md").write_text("# no date\n- **Status:** IN MOTION\n")
    assert "no-date" in run("stale_check.py", home, AGENT2_TODAY="2026-09-30").stdout


# ── roll-up ────────────────────────────────────────────────────────────────

def test_rollup_posts_when_ok_and_pauses_at_warn(home):
    tracker(home, "vendors", "synthetic-stedi", "2026-09-29")
    assert "synthetic-stedi" in run("tracker_rollup.py", home).stdout
    (home / "state" / "budget.json").write_text(json.dumps({"state": "warn"}))
    assert run("tracker_rollup.py", home).stdout == ""
    assert "synthetic-stedi" in (home / "trackers" / "README.md").read_text()


# ── draft check ────────────────────────────────────────────────────────────

GOOD = """---
template: follow-up.md
kind: vendor-email
tracker: vendors/synthetic-stedi.md
to: partners@example.com
---

## Email
Subject: Re: enrollment API access

Hi team,

Following up on our note from last week about enrollment API access. Could you share the next step?

Rick Hennessey, FinVerified

## Facts used
- Original message sent 2026-09-23 [S1]
- Per-transaction pricing for enrollment NOT CONFIRMED

## Sources
- [S1] tracker:vendors/synthetic-stedi.md
"""


def queue(home: Path, name: str, text: str) -> None:
    (home / "drafts" / "pending" / name).write_text(text)


def test_good_draft_posts_and_moves(home):
    tracker(home, "vendors", "synthetic-stedi", "2026-09-23")
    queue(home, "d1.md", GOOD)
    r = run("draft_check.py", home)
    assert "READY FOR RICK TO SEND" in r.stdout and "Following up" in r.stdout
    assert (home / "drafts" / "posted" / "d1.md").exists()
    assert not (home / "drafts" / "pending" / "d1.md").exists()


@pytest.mark.parametrize("mutate,reason", [
    (lambda t: t.replace("template: follow-up.md", "template: made-up.md"), "not an approved template"),
    (lambda t: t.replace("## Sources\n", "## Refs\n"), "missing section `## Sources`"),
    (lambda t: t.replace("Could you", "{{ask}} Could you"), "placeholder"),
    (lambda t: t.replace("2026-09-23 [S1]", "2026-09-23"), "unsourced fact"),
    (lambda t: t.replace("[S1] tracker:vendors/synthetic-stedi.md", "[S1] tracker:vendors/nope.md"), "does not exist"),
    (lambda t: t.replace("Could you share", "We will sign and could you share"), "prohibited claim"),
    (lambda t: t.replace("Could you share", "We are HIPAA-certified. Could you share"), "prohibited claim"),
    (lambda t: t.replace("Could you share", "Routing 021000021, could you share"), "routing"),
    (lambda t: t.replace("Could you share", "Patient name Jane Test, could you share"), "patient"),
    (lambda t: t.replace("Could you share", "SSN 123-45-6789, could you share"), "SSN"),
])
def test_bad_draft_fails_and_is_not_posted(home, mutate, reason):
    tracker(home, "vendors", "synthetic-stedi", "2026-09-23")
    queue(home, "bad.md", mutate(GOOD))
    r = run("draft_check.py", home)
    assert "failed the quality check" in r.stdout and reason in r.stdout
    assert "READY FOR RICK TO SEND" not in r.stdout
    assert (home / "drafts" / "failed" / "bad.md").exists()


def test_npi_and_tin_are_allowed_provider_facts(home):
    tracker(home, "practices", "test-family-dental", "2026-09-29")
    text = (ROOT / "templates" / "drafts" / "enrollment-request.md").read_text()
    for k, v in {
        "{{slug}}": "test-family-dental", "{{payer name}}": "Synthetic Payer",
        "{{clearinghouse enrollment API | payer portal (Rick submits) | paper form (practice signs)}}": "clearinghouse enrollment API",
        "{{payer/clearinghouse}}": "the clearinghouse",
        "{{https://payer or clearinghouse enrollment page}}": "https://example.com/enroll",
    }.items():
        text = text.replace(k, v)
    text = (text.replace("Legal name: {{}}", "Legal name: Test Family Dental PLLC")
                .replace("Group NPI: {{}}", "Group NPI: 1234567893")
                .replace("TIN/EIN: {{}}", "TIN/EIN: 12-3456789")
                .replace("Practice address: {{}}", "Practice address: 1 Test St, Testville")
                .replace("Enrollment contact: {{name, business email}}", "Enrollment contact: Office Manager, office@example.com")
                .replace("{{What is being requested: ERA, EFT, eligibility or a combination, and through which route.}}", "ERA and EFT via the clearinghouse.")
                .replace("{{payer/clearinghouse requirement, e.g. signed authorization, voided-check upload by the practice}}", "Signed authorization from the practice")
                .replace("{{signatures, attestations}}", "Authorization signature"))
    queue(home, "enroll.md", text)
    r = run("draft_check.py", home)
    assert "READY FOR RICK TO SEND" in r.stdout, r.stdout


def test_empty_queue_is_silent(home):
    assert run("draft_check.py", home).stdout == ""


# ── weekly spend ───────────────────────────────────────────────────────────

def test_weekly_spend_by_model_and_opus_reasons(home):
    log = home / "logs" / "spend.jsonl"
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    rows = [
        {"dt": (now - timedelta(days=6)).isoformat(), "job": "budget_guard", "key_spend_usd": 1.0,
         "key_max_budget_usd": 25.0, "pct": 4.0, "model_spend": {"agent2-claude-haiku": 0.5, "agent2-claude-sonnet": 0.5}},
        {"dt": (now - timedelta(days=1)).isoformat(), "job": "stale_check"},
        {"dt": now.isoformat(), "job": "budget_guard", "key_spend_usd": 4.0, "key_max_budget_usd": 25.0,
         "pct": 16.0, "model_spend": {"agent2-claude-haiku": 1.0, "agent2-claude-sonnet": 2.0, "agent2-claude-opus": 1.0}},
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    (home / "logs" / "opus" / "reasons.md").write_text(
        f"{now.date()} | practices/test-family-dental.md | conflicting MCO enrollment sources\n")
    out = run("spend_report.py", home).stdout
    assert "Total model spend: $3.00" in out
    assert "drafts and call briefs (Sonnet 5.5): $1.50" in out
    assert "hard research (Opus 5.5): $1.00" in out
    assert "stale_check: 1 runs" in out
    assert "Opus escalations: 1" in out and "conflicting MCO" in out
