"""AI budget: Sol reads his own spend from LiteLLM and tells Rick. No hard stop at the plan.

Thresholds (config `sol.budget`): warn_at 15, notify_at 20 (keep working),
ceiling alert at 90% of the $100 safety ceiling. Sol NEVER writes to LiteLLM:
only GET /key/info and GET /spend/logs are allowed here, and a raise is done by
Rick himself in LiteLLM (we only hand him the link).
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from . import common, slack_dm, usage_ledger

ALLOWED_PATHS = ("/key/info", "/spend/logs")
DEFAULTS = {"monthly_plan_usd": 20, "warn_at": 15, "notify_at": 20, "safety_ceiling": 100,
            "ceiling_alert_percent": 90, "litellm_ui_url": ""}


def _cfg() -> Dict[str, Any]:
    c = dict(DEFAULTS)
    c.update((common.sol_config().get("budget") or {}))
    return c


def _get(path: str) -> Any:
    """Read-only LiteLLM call with Sol's own key. Anything but an allowed GET path is refused."""
    if not any(path.startswith(p) for p in ALLOWED_PATHS):
        raise PermissionError(f"Sol may not call LiteLLM {path}; budget changes are Rick's, in LiteLLM")
    base = os.environ.get("OPENAI_BASE_URL", "").rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return common.http_json("GET", base + path,
                            headers={"Authorization": "Bearer " + os.environ.get("OPENAI_API_KEY", "")})


def _breakdown() -> List[Dict[str, Any]]:
    """Best effort: spend by model this month. Empty if LiteLLM won't serve it to a virtual key."""
    try:
        rows = _get("/spend/logs?summarize=true") or []
    except Exception:
        return []
    out: Dict[str, float] = {}
    for r in rows if isinstance(rows, list) else []:
        for k, v in (r.get("models") or {}).items():
            out[k] = out.get(k, 0.0) + float(v or 0)
    return [{"model": k, "usd": round(v, 4)} for k, v in sorted(out.items(), key=lambda kv: -kv[1])]


def status() -> Dict[str, Any]:
    c = _cfg()
    source = "litellm"
    try:
        info = (_get("/key/info") or {}).get("info", {})
        spend = float(info.get("spend") or 0)
        ceiling = float(info.get("max_budget") or c["safety_ceiling"])
        breakdown = _breakdown()
    except (common.HttpError, PermissionError):
        # Sol's virtual key may not be allowed to read /key/info. Fall back to the local estimate.
        spend, breakdown = usage_ledger.estimate_month()
        ceiling, source = float(c["safety_ceiling"]), "estimate"
    return {"spent_usd": round(spend, 4), "plan_usd": c["monthly_plan_usd"], "safety_ceiling_usd": ceiling,
            "pct_of_ceiling": round(100 * spend / ceiling, 1) if ceiling else None, "source": source,
            "breakdown": breakdown, "raise_link": c["litellm_ui_url"]}


def _month() -> str:
    return time.strftime("%Y-%m")


def evaluate(spend: float, sent: Dict[str, bool], c: Dict[str, Any]) -> List[str]:
    """Pure: which alerts are due given spend and which were already sent this month."""
    due: List[str] = []
    if spend >= c["warn_at"] and not sent.get("warn"):
        due.append("warn")
    if spend >= c["notify_at"] and not sent.get("notify"):
        due.append("notify")
    if spend >= c["safety_ceiling"] * c["ceiling_alert_percent"] / 100 and not sent.get("ceiling"):
        due.append("ceiling")
    return due


def message(kind: str, st: Dict[str, Any], c: Dict[str, Any], todo: str) -> str:
    uses = ", ".join(f"{b['model']} ${b['usd']:.2f}" for b in st["breakdown"][:4]) or "see LiteLLM for the per-model split"
    if kind == "ceiling":
        return (f"I'm near my safety limit. Reply RAISE 50 to add $50 or RAISE 100 to add $100.\n"
                f"Spent ${st['spent_usd']:.2f}{' (estimated)' if st.get('source') == 'estimate' else ''} of ${st['safety_ceiling_usd']:.0f}. Spend so far: {uses}.\n"
                f"I can't change my own budget. To raise it yourself in LiteLLM: {c['litellm_ui_url']}")
    plan = c["monthly_plan_usd"]
    label = f"75% of my ${plan} monthly plan" if kind == "warn" else f"100% of my ${plan} monthly plan. I'm still working"
    est = " (estimated from my own usage log; LiteLLM won't let my key read its spend)" if st.get("source") == "estimate" else ""
    return (f"AI spend check: ${st['spent_usd']:.2f} spent{est}, which is {label}.\n"
            f"Spent on: {uses}.\nLeft to do: {todo}")


def check_and_notify(todo: str = "weekly report, month-end close, vendor register upkeep") -> Dict[str, Any]:
    """Daily scripted check. De-duplicated per month so Rick gets each alert once."""
    c, st = _cfg(), status()
    state = common.load_state("budget_state.json", {})
    if state.get("month") != _month():
        state = {"month": _month(), "sent": {}}
    sent = state.setdefault("sent", {})
    due = evaluate(st["spent_usd"], sent, c)
    # warn+notify can both be due on a jump; send the higher one only
    if "notify" in due and "warn" in due:
        sent["warn"] = True
        due.remove("warn")
    delivered = []
    for kind in due:
        r = slack_dm.dm_rick(message(kind, st, c, todo))
        if r.get("ok"):
            sent[kind] = True
            delivered.append(kind)
    common.save_state("budget_state.json", state)
    return {"status": st, "alerts_sent": delivered, "alerts_failed": [k for k in due if k not in delivered]}
