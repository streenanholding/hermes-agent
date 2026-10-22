#!/usr/bin/env python3
"""80% AI-budget warning (no_agent cron, no model call).

Reads this agent's own LiteLLM virtual key (spend vs max_budget) and, the first
time spend crosses ``BUDGET_WARN_PCT`` (default 80) in a budget period, asks
Rick one question with the raise link. Never posts twice for the same period.
Stdout is empty (silent run) unless it posts. It never writes to LiteLLM.

Env: OPENAI_BASE_URL / OPENAI_API_KEY (the agent's own key; falls back to
model.base_url in nothing else), LITELLM_UI_URL (raise link, optional),
BUDGET_WARN_PCT, HERMES_HOME (state file), BUDGET_WARN_SIMULATE (tests: "spend,max").
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, os.environ.get("HERMES_INSTALL_DIR", "/opt/hermes"))


def warn_pct() -> float:
    try:
        return float(os.environ.get("BUDGET_WARN_PCT", "80"))
    except ValueError:
        return 80.0


def fetch_key_info() -> dict:
    sim = os.environ.get("BUDGET_WARN_SIMULATE")
    if sim:
        spend, cap = (float(x) for x in sim.split(","))
        return {"spend": spend, "max_budget": cap, "budget_reset_at": "sim"}
    base = os.environ["OPENAI_BASE_URL"].rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    req = urllib.request.Request(f"{base}/key/info", headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read())
    return body.get("info") or body


def state_path() -> Path:
    return Path(os.environ.get("HERMES_HOME", "/opt/data")) / "state" / "budget_warn.json"


def decide(info: dict, last_period: "str | None", pct_limit: float) -> "tuple[str | None, str]":
    """Return (message or None, period id). Pure so it is unit-testable."""
    cap = info.get("max_budget")
    period = str(info.get("budget_reset_at") or "no-reset")
    if not cap:
        return None, period
    spend = float(info.get("spend") or 0.0)
    pct = 100.0 * spend / float(cap)
    if pct < pct_limit or last_period == period:
        return None, period
    link = os.environ.get("LITELLM_UI_URL", "")
    msg = (f"AI budget at {pct:.0f}% (${spend:.2f} of ${float(cap):.2f}). I keep working; "
           f"reply if you want it raised." + (f" Raise it here: {link}" if link else ""))
    return msg, period


def main() -> int:
    try:
        info = fetch_key_info()
    except Exception as exc:  # LiteLLM down: the health loop owns that failure, stay quiet
        print(f"budget_warn: could not read key info ({type(exc).__name__})", file=sys.stderr)
        return 0
    path = state_path()
    try:
        last = json.loads(path.read_text()).get("period")
    except (OSError, ValueError):
        last = None
    msg, period = decide(info, last, warn_pct())
    if not msg:
        return 0
    from gateway import ops_alerts

    ops_alerts.notify_rick(msg, key=f"budget-warn:{period}")
    if ops_alerts.flush_pending():  # only remember the period once Rick was actually told
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"period": period}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
