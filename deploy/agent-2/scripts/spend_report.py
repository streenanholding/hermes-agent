#!/usr/bin/env python3
"""Weekly spend summary (no_agent cron, Mondays). Essential: runs at warn.

Built from /opt/data/logs/spend.jsonl, which only this agent's scripts write:
  - budget_guard rows carry the key's cumulative spend and per-model spend
    (LiteLLM key info). Spend for the week = last snapshot minus first, per
    model alias. Each alias maps to one job class (see TIER below).
  - script job rows are counted as runs at $0.
  - Opus escalations are counted from /opt/data/logs/opus/reasons.md.
"""

from __future__ import annotations

import json
import sys

import agent2_common as c

TIER = {
    "agent2-claude-haiku": "tracking, status answers, stale/inbox sorting (Haiku 4.5)",
    "agent2-claude-sonnet": "drafts and call briefs (Sonnet 5.5)",
    "agent2-claude-opus": "hard research (Opus 5.5)",
}


def load_rows(since: c.dt.datetime) -> list[dict]:
    rows = []
    try:
        for line in c.SPEND_LOG.read_text().splitlines():
            try:
                row = json.loads(line)
                if c.dt.datetime.fromisoformat(row["dt"]) >= since:
                    rows.append(row)
            except (ValueError, KeyError):
                continue
    except OSError:
        pass
    return rows


def delta(first: dict, last: dict) -> dict:
    out = {}
    for model, val in (last or {}).items():
        d = float(val or 0) - float((first or {}).get(model) or 0)
        # A negative delta means LiteLLM reset the counter mid-week; use the last value.
        out[model] = d if d >= 0 else float(val or 0)
    return out


def main() -> int:
    since = c.now_utc() - c.dt.timedelta(days=7)
    rows = load_rows(since)
    guard = [r for r in rows if r.get("job") == "budget_guard" and "key_spend_usd" in r]
    runs: dict[str, int] = {}
    for r in rows:
        if r.get("job") not in ("budget_guard", "spend_report"):
            runs[r["job"]] = runs.get(r["job"], 0) + 1

    out = [f"*Agent 2 weekly spend, {since.date()} to {c.today()}*"]
    if len(guard) >= 2:
        total = guard[-1]["key_spend_usd"] - guard[0]["key_spend_usd"]
        if total < 0:
            total = guard[-1]["key_spend_usd"]
        out.append(f"Total model spend: ${total:.2f}  (budget used now: {guard[-1].get('pct', 0):.0f}% "
                   f"of ${guard[-1].get('key_max_budget_usd') or 0:.2f})")
        by_model = delta(guard[0].get("model_spend"), guard[-1].get("model_spend"))
        if by_model:
            out.append("\nBy job class:")
            for model, usd in sorted(by_model.items(), key=lambda kv: -kv[1]):
                out.append(f"• {TIER.get(model, model)}: ${usd:.2f}")
        else:
            out.append("Per-model split unavailable: LiteLLM key info returned no model_spend.")
    else:
        out.append("Not enough budget-guard snapshots this week to compute spend.")

    if runs:
        out.append("\nScheduled script jobs ($0, no model):")
        out += [f"• {job}: {n} runs" for job, n in sorted(runs.items())]

    opus = []
    try:
        for line in c.OPUS_REASONS.read_text().splitlines():
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3 and parts[0][:10] >= str(since.date()):
                opus.append(f"• {parts[0][:10]} {parts[1]}: {parts[2]}")
    except OSError:
        pass
    out.append(f"\nOpus escalations: {len(opus)}")
    out += opus

    c.log_spend("spend_report", opus_escalations=len(opus))
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
