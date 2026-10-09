#!/usr/bin/env python3
"""Weekday tracker roll-up (no_agent cron). Non-essential: silent at warn/stop.

One line per tracker: status, owner, next action. Grouped by vendors and
practices. Also rewrites /opt/data/trackers/README.md as the index.
"""

from __future__ import annotations

import sys

import agent2_common as c


def main() -> int:
    state = c.budget_state()
    rows = {"vendors": [], "practices": []}
    for kind, path in c.iter_trackers():
        text = path.read_text()
        rows[kind].append((
            path.stem,
            c.tracker_field(text, "Status") or "NO STATUS",
            c.tracker_field(text, "Owner") or "unassigned",
            c.tracker_field(text, "Next action") or "none recorded",
        ))

    index = ["# Tracker index", "", "Rewritten by tracker_rollup.py. Do not edit by hand.", ""]
    for kind, items in rows.items():
        index.append(f"## {kind.title()}")
        index += [f"- [{s}]({kind}/{s}.md) | {st} | {o} | {n}" for s, st, o, n in items] or ["- none"]
        index.append("")
    c.TRACKERS.mkdir(parents=True, exist_ok=True)
    (c.TRACKERS / "README.md").write_text("\n".join(index))

    c.log_spend("tracker_rollup", trackers=sum(len(v) for v in rows.values()), budget_state=state)
    if state != "ok" or not any(rows.values()):
        return 0  # paused at warn/stop, or nothing tracked yet

    out = [f"*Tracker roll-up, {c.today()}*"]
    for kind, items in rows.items():
        if items:
            out.append(f"\n_{kind.title()}_")
            out += [f"• *{s}*: {st} ({o}). Next: {n}" for s, st, o, n in items]
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
