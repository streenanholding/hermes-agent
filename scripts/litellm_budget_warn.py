#!/usr/bin/env python3
"""Warn in Slack when an agent's LiteLLM virtual key reaches 80% of max_budget.

Run on a schedule (e.g. a Railway cron or a Hermes ``no_agent`` cron job) so
budgets get raised BEFORE a key starts rejecting calls (which trips the
gateway auth gate and blocks the agent).

For each agent (sol, carly, seraphine, carol) it looks up the agent's virtual
key by ``key_alias`` with the LiteLLM admin key, compares ``spend`` to
``max_budget`` and posts ONE Slack message per key per budget period when the
ratio crosses the threshold. State lives in a small JSON file so reruns stay
quiet until the key drops back under the threshold or its budget resets.

Usage (from the repo root):
    python3 scripts/litellm_budget_warn.py [--threshold 80] [--dry-run]
        [--alias sol=hermes-sol ...] [--state-file PATH]

Env:
    LITELLM_BASE_URL     LiteLLM root, e.g. https://litellm-gateway-...app
    LITELLM_MASTER_KEY   admin key (secret; never printed)
    SLACK_BOT_TOKEN      for the alert (targets: hardening.alerts in config.yaml)
Key aliases default to the agent name; override with --alias NAME=ALIAS.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

AGENTS = ["sol", "carly", "seraphine", "carol"]
DEFAULT_THRESHOLD_PCT = 80.0


def _default_state_file() -> Path:
    home = os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes")
    return Path(home) / "state" / "litellm_budget_warn.json"


def fetch_key(base_url: str, admin_key: str, alias: str) -> Optional[Dict[str, Any]]:
    """Return the LiteLLM key record for ``alias`` (spend, max_budget, ...)."""
    qs = urllib.parse.urlencode({"key_alias": alias, "return_full_object": "true"})
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/key/list?{qs}",
        headers={"Authorization": f"Bearer {admin_key}"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read())
    keys = body.get("keys") or []
    return keys[0] if keys and isinstance(keys[0], dict) else None


def evaluate(
    agent: str, info: Dict[str, Any], state: Dict[str, Any], threshold_pct: float
) -> Optional[str]:
    """Return the warning text if ``agent`` newly crossed the threshold.

    Mutates ``state`` (the dedup record). Returns None when there is nothing to
    say: under threshold, no max_budget, or already warned this period.
    """
    cap = info.get("max_budget")
    spend = float(info.get("spend") or 0.0)
    if not cap:
        return None
    pct = 100.0 * spend / float(cap)
    period = str(info.get("budget_reset_at") or "")
    prev = state.get(agent) or {}
    if pct < threshold_pct:
        state.pop(agent, None)  # healed / reset: allow a future warning
        return None
    if prev.get("period") == period:
        return None
    state[agent] = {"period": period, "pct": round(pct, 1)}
    reset = f" Resets {period[:10]}." if period else ""
    return (
        f"💸 {agent.capitalize()}'s LiteLLM key is at {pct:.0f}% of its budget "
        f"(${spend:.2f} of ${float(cap):.2f}).{reset} "
        "Raise max_budget in LiteLLM before it blocks the agent."
    )


def load_state(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n")


def run(
    *,
    aliases: Dict[str, str],
    threshold_pct: float,
    state_file: Path,
    dry_run: bool,
    fetch=fetch_key,
    post=None,
) -> List[str]:
    base = os.environ.get("LITELLM_BASE_URL", "")
    admin = os.environ.get("LITELLM_MASTER_KEY", "")
    if not base or not admin:
        raise SystemExit("LITELLM_BASE_URL and LITELLM_MASTER_KEY must be set")
    if post is None:
        from gateway.ops_alerts import post_slack_alert as post
    state = load_state(state_file)
    messages: List[str] = []
    for agent, alias in aliases.items():
        try:
            info = fetch(base, admin, alias)
        except Exception as exc:
            print(f"{agent}: could not read key '{alias}' ({type(exc).__name__})", file=sys.stderr)
            continue
        if info is None:
            print(f"{agent}: no LiteLLM key with alias '{alias}'", file=sys.stderr)
            continue
        msg = evaluate(agent, info, state, threshold_pct)
        if msg:
            messages.append(msg)
            print(msg)
            if not dry_run and not post(msg):
                # Slack failed: forget the dedup record so the next run retries.
                state.pop(agent, None)
    if not dry_run:
        save_state(state_file, state)
    return messages


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD_PCT)
    ap.add_argument("--alias", action="append", default=[], metavar="NAME=ALIAS")
    ap.add_argument("--state-file", type=Path, default=_default_state_file())
    ap.add_argument("--dry-run", action="store_true", help="print, don't post or save state")
    args = ap.parse_args(argv)
    aliases = {a: a for a in AGENTS}
    for item in args.alias:
        name, _, alias = item.partition("=")
        if name not in aliases or not alias:
            ap.error(f"--alias expects one of {AGENTS} as NAME=ALIAS, got {item!r}")
        aliases[name] = alias
    run(aliases=aliases, threshold_pct=args.threshold, state_file=args.state_file, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
