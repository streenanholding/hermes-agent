#!/usr/bin/env python3
"""Hourly budget guard (no_agent cron). Warn at 80%, stop at 100%.

Reads this agent's own LiteLLM virtual key info (spend vs max_budget), writes
/opt/data/state/budget.json, and prints a Slack message only when the state
changes (ok -> warn, warn -> stop, or back to ok after LiteLLM's weekly reset).

LiteLLM enforces the hard stop itself: at 100% it rejects model calls on the
key. This script makes the agent and the other jobs aware of it, and pauses
non-essential work at 80%.

Env:
  AGENT2_LITELLM_BASE_URL  LiteLLM root, e.g. https://litellm-gateway-...app
  AGENT2_LITELLM_KEY       the agent's virtual key (Railway reference to OPENAI_API_KEY)
  AGENT2_BUDGET_SIMULATE_SPEND_PCT  tests/drills only: skip LiteLLM, use this %
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

import agent2_common as c


def fetch_key_info() -> dict:
    base = os.environ["AGENT2_LITELLM_BASE_URL"].rstrip("/")
    key = os.environ["AGENT2_LITELLM_KEY"]
    req = urllib.request.Request(f"{base}/key/info", headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read())
    return body.get("info") or body


def read_usage() -> tuple[float, float | None, dict, str | None]:
    """(spend_usd, max_budget_usd, model_spend, budget_reset_at)."""
    sim = os.environ.get("AGENT2_BUDGET_SIMULATE_SPEND_PCT")
    if sim is not None:
        return float(sim), 100.0, {}, None
    info = fetch_key_info()
    return (
        float(info.get("spend") or 0.0),
        float(info["max_budget"]) if info.get("max_budget") is not None else None,
        info.get("model_spend") or {},
        info.get("budget_reset_at"),
    )


def main() -> int:
    try:
        spend, cap, model_spend, reset_at = read_usage()
    except KeyError as exc:
        print(f"Budget guard misconfigured: missing env var {exc.args[0]}. Budget state unchanged.")
        return 1
    except Exception as exc:  # network / LiteLLM down
        print(f"Budget guard could not read LiteLLM key info ({type(exc).__name__}). Budget state unchanged.")
        return 1

    if not cap:
        state, pct = "warn", 0.0
        note = "No max_budget is set on the LiteLLM key, so there is no hard cap. Set one in LiteLLM."
    else:
        pct = 100.0 * spend / cap
        state = c.classify(pct)
        note = None

    previous = c.budget_state()
    c.STATE.mkdir(parents=True, exist_ok=True)
    c.BUDGET_FILE.write_text(json.dumps({
        "state": state,
        "pct": round(pct, 1),
        "spend_usd": round(spend, 4),
        "max_budget_usd": cap,
        "budget_reset_at": reset_at,
        "checked_at": c.now_utc().isoformat(),
    }, indent=2) + "\n")
    c.log_spend("budget_guard", usd=0.0, key_spend_usd=round(spend, 4),
                key_max_budget_usd=cap, pct=round(pct, 1), model_spend=model_spend)

    if note and previous != "warn":
        print(f"{c.rick_mention()} {note}")
    elif state == previous:
        return 0  # silent: nothing changed
    elif state == "warn":
        print(f"{c.rick_mention()} Agent 2 has used {pct:.0f}% of its weekly budget "
              f"(${spend:.2f} of ${cap:.2f}). Non-essential work is paused: no tracker "
              "roll-ups, proactive research, Opus or skill writing. Status answers, stale "
              "checks, draft checks and drafts you ask for continue.")
    elif state == "stop":
        print(f"{c.rick_mention()} Agent 2 hit its weekly budget cap (${spend:.2f} of ${cap:.2f}). "
              "LiteLLM is rejecting its model calls and all scheduled jobs are silent until the "
              "weekly reset. Raise the cap in LiteLLM if you need it sooner.")
    elif state == "ok":
        print(f"Agent 2 budget is back under 80% ({pct:.0f}%). Normal work resumed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
