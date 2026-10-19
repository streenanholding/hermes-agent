"""Shared helpers for Agent 2's cron scripts (stdlib only).

Every scheduled job is a Hermes ``no_agent`` cron script: stdout is delivered
to Slack verbatim, empty stdout is a silent run, and no model is called.

Secrets are read from the environment at run time and never printed or logged.
Hermes strips provider credentials (OPENAI_API_KEY etc.) from script
subprocesses, so the budget guard reads its key from AGENT2_LITELLM_KEY, a
Railway reference to the same virtual key.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.request
from pathlib import Path

DATA = Path(os.environ.get("AGENT2_DATA_DIR") or os.environ.get("HERMES_HOME") or "/opt/data")
TRACKERS = DATA / "trackers"
DRAFTS = DATA / "drafts"
TEMPLATES = DATA / "templates"
STATE = DATA / "state"
LOGS = DATA / "logs"
BUDGET_FILE = STATE / "budget.json"
SPEND_LOG = LOGS / "spend.jsonl"
OPUS_REASONS = LOGS / "opus" / "reasons.md"

WARN_PCT = 80.0
STOP_PCT = 100.0

LAST_MOVEMENT_RE = re.compile(r"^\s*-\s*\*\*Last movement:\*\*\s*(\d{4}-\d{2}-\d{2})", re.M)
FIELD_RE = r"^\s*-\s*\*\*{name}:\*\*\s*(.+)$"


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def today() -> dt.date:
    override = os.environ.get("AGENT2_TODAY")  # tests only
    return dt.date.fromisoformat(override) if override else dt.date.today()


def business_days_between(start: dt.date, end: dt.date) -> int:
    """Weekdays after ``start`` up to and including ``end``. Holidays not excluded."""
    if end <= start:
        return 0
    days = 0
    d = start
    while d < end:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            days += 1
    return days


def tracker_field(text: str, name: str) -> str | None:
    m = re.search(FIELD_RE.format(name=re.escape(name)), text, re.M)
    return m.group(1).strip() if m else None


def iter_trackers():
    for kind in ("vendors", "practices"):
        folder = TRACKERS / kind
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.md")):
            if path.name.lower() == "readme.md":
                continue
            yield kind, path


# ── Budget state ───────────────────────────────────────────────────────────

def budget_state() -> str:
    """'ok' | 'warn' | 'stop'. Missing or unreadable file reads as 'ok' so a
    fresh volume still runs; the budget guard writes it within the hour."""
    try:
        return json.loads(BUDGET_FILE.read_text()).get("state", "ok")
    except (OSError, ValueError):
        return "ok"


def classify(pct: float) -> str:
    if pct >= STOP_PCT:
        return "stop"
    if pct >= WARN_PCT:
        return "warn"
    return "ok"


# ── Spend logging ──────────────────────────────────────────────────────────

def log_spend(job: str, *, model: str | None = None, tokens: int = 0, usd: float = 0.0, **extra) -> None:
    """Append one JSON line to spend.jsonl and ship it to Better Stack if set.

    Never pass PHI, secrets or message content here: job names, model aliases,
    counts and dollars only.
    """
    row = {
        "dt": now_utc().isoformat(),
        "service": "hermes-agent-2",
        "job": job,
        "model": model,
        "tokens": tokens,
        "usd": round(usd, 6),
        **extra,
    }
    LOGS.mkdir(parents=True, exist_ok=True)
    with SPEND_LOG.open("a") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    ship_to_better_stack(row)


def ship_to_better_stack(row: dict) -> None:
    token = os.environ.get("AGENT2_BETTER_STACK_SOURCE_TOKEN")
    host = os.environ.get("AGENT2_BETTER_STACK_INGESTING_HOST")
    if not token or not host:
        return  # cleanly disabled when unset
    req = urllib.request.Request(
        f"https://{host}",
        data=json.dumps(row).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10).close()
    except Exception:
        # Shipping is best-effort; the local jsonl line is the record.
        # Never echo the token or the response body.
        pass


def rick_mention() -> str:
    uid = os.environ.get("AGENT2_RICK_SLACK_ID", "").strip()
    return f"<@{uid}>" if uid else "Rick"
