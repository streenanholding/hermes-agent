#!/usr/bin/env python3
"""Daily stale check (no_agent cron, weekdays). Essential: runs at warn and stop (it costs $0).

5 business days with no movement -> flagged. 10 -> escalated to Rick.
Reads `- **Last movement:** YYYY-MM-DD` from each tracker. A tracker without
that line is flagged too, since it can't be checked.
"""

from __future__ import annotations

import sys

import agent2_common as c

FLAG_DAYS = 5
ESCALATE_DAYS = 10
CLOSED = {"LIVE", "ENROLLED", "CLOSED", "NOT PURSUING"}


def main() -> int:
    today = c.today()
    flagged, escalated, unreadable = [], [], []
    for kind, path in c.iter_trackers():
        text = path.read_text()
        status = (c.tracker_field(text, "Status") or "").upper()
        if any(status.startswith(s) for s in CLOSED):
            continue
        m = c.LAST_MOVEMENT_RE.search(text)
        if not m:
            unreadable.append(f"{kind}/{path.stem}")
            continue
        last = c.dt.date.fromisoformat(m.group(1))
        days = c.business_days_between(last, today)
        nxt = c.tracker_field(text, "Next action") or "no next action recorded"
        line = f"• *{kind}/{path.stem}*: {days} business days since {last} ({status or 'no status'}). Next: {nxt}"
        if days >= ESCALATE_DAYS:
            escalated.append(line)
        elif days >= FLAG_DAYS:
            flagged.append(line)

    c.log_spend("stale_check", flagged=len(flagged), escalated=len(escalated), unreadable=len(unreadable))
    if not (flagged or escalated or unreadable):
        return 0  # silent

    out = [f"*Stale check, {today}*"]
    if escalated:
        out.append(f"\n{c.rick_mention()} escalated, {ESCALATE_DAYS}+ business days with no movement:")
        out += escalated
    if flagged:
        out.append(f"\nFlagged, {FLAG_DAYS}+ business days:")
        out += flagged
    if unreadable:
        out.append("\nNo `Last movement` date, can't check: " + ", ".join(unreadable))
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
