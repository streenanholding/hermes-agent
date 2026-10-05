"""Model-facing tools. Nine consolidated tools (one schema each) to keep the per-call footprint small.

Every result is PII-scrubbed. The approver identity for approvals is read from the
gateway session, never from model arguments, and DMs only ever go to Rick.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict

from . import (approvals, aws_costs, budget, drive, fraud, gmail, mercury, pii, slack_dm, stripe_api, xero)


def _out(obj: Any) -> str:
    return json.dumps(pii.scrub_obj(obj), default=str)


def _run(fn: Callable[[], Any]) -> str:
    try:
        return _wrap(fn)
    except Exception as e:  # policy errors are expected and shown plainly
        return _out({"success": False, "error": f"{type(e).__name__}: {e}"})


def _wrap(fn: Callable[[], Any]) -> str:
    res = fn()
    return _out({"success": True, **res} if isinstance(res, dict) else {"success": True, "data": res})


def _schema(name: str, desc: str, actions: Dict[str, str], extra: Dict[str, Any] = None) -> Dict[str, Any]:
    props: Dict[str, Any] = {"action": {"type": "string", "enum": list(actions), "description": "; ".join(f"{k}: {v}" for k, v in actions.items())}}
    props.update(extra or {})
    return {"name": name, "description": desc, "parameters": {"type": "object", "properties": props, "required": ["action"]}}


def _s(d: str) -> Dict[str, Any]:
    return {"type": "string", "description": d}


def h_mercury(args, **_):
    a = args.get("action")
    if a == "accounts":
        return _run(mercury.accounts)
    if a == "transactions":
        return _run(lambda: mercury.transactions(args["account_id"], args.get("start"), args.get("end"), args.get("limit", 200)))
    return _out({"success": False, "error": "unknown action"})


def h_stripe(args, **_):
    a = args.get("action")
    if a == "summary":
        return _run(stripe_api.summary)
    return _run(lambda: {"data": stripe_api.get(a, limit=args.get("limit", 25))})


def h_xero(args, **_):
    a = args.get("action")
    if a == "connect_link":
        return _run(lambda: {"url": xero.authorize_url(), "redirect_uri": xero.redirect_uri()})
    if a == "org":
        return _run(lambda: {"organisation": xero.org_name()})
    if a == "read":
        return _run(lambda: {"data": xero.read(args["endpoint"])})
    if a == "post_draft":
        return _run(lambda: {"data": xero.post_draft(args["endpoint"], args["payload"])})
    return _out({"success": False, "error": "unknown action"})


def h_aws(args, **_):
    a = args.get("action")
    if a == "cost_by_month":
        return _run(lambda: aws_costs.cost_by_month(args.get("start")))
    if a == "budgets":
        return _run(aws_costs.budgets)
    return _out({"success": False, "error": "unknown action"})


def h_drive(args, **_):
    a = args.get("action")
    if a == "shared_drives":
        return _run(lambda: {"drives": drive.shared_drives()})
    if a == "list":
        return _run(lambda: drive.list_folder(args["folder_id"]))
    if a == "read":
        return _run(lambda: {"text": drive.read_text(args["file_id"])[:20000]})
    if a == "create_folder":
        return _run(lambda: drive.create_folder(args["name"], args["parent_id"]))
    if a == "create_sheet":
        return _run(lambda: drive.create_sheet_from_csv(args["name"], args["parent_id"], args["csv"]))
    return _out({"success": False, "error": "unsupported: Sol cannot delete, rename, or move Drive files"})


def h_gmail(args, **_):
    a = args.get("action")
    if a == "search":
        return _run(lambda: gmail.search(args.get("query", "newer_than:7d"), args.get("max_results", 10)))
    if a == "connect_link":
        return _run(lambda: {"url": gmail.authorize_url()})
    return _out({"success": False, "error": "unknown action"})


def h_dm(args, **_):
    return _run(lambda: slack_dm.dm_rick(args.get("text", "")))


def _sender() -> str:
    from gateway.session_context import get_session_env

    return get_session_env("HERMES_SESSION_USER_ID", "")


def h_approval(args, **_):
    a, item = args.get("action"), args.get("item_id", "")
    if a == "propose":
        return _run(lambda: {"item": approvals.propose(item, args.get("kind", "general"), args.get("payload", {}))})
    if a == "record":
        text, uid = args.get("text", ""), _sender()
        raise_amt = approvals.parse_raise(text, uid)
        if raise_amt:
            link = budget._cfg()["litellm_ui_url"]
            return _out({"success": True, "raise_request": raise_amt,
                         "next": f"Valid from Rick. I cannot change my own budget. Send Rick this link to add ${raise_amt}: {link}"})
        ok, why = approvals.approve(item, uid)
        return _out({"success": ok, "result": why})
    if a == "check":
        return _out({"approved": approvals.is_approved(item, args.get("payload", {}))})
    return _out({"success": False, "error": "unknown action"})


def h_budget(args, **_):
    a = args.get("action")
    if a == "status":
        return _run(budget.status)
    if a == "check_and_notify":
        return _run(lambda: budget.check_and_notify(args.get("todo", "weekly report, month-end close, vendor register upkeep")))
    return _out({"success": False, "error": "unknown action"})


TOOLS = [
    ("sol_mercury", "🏦", h_mercury, _schema("sol_mercury", "Mercury bank, READ ONLY: accounts and balances, transactions. Cannot move money.",
        {"accounts": "accounts and balances (last four only)", "transactions": "transactions for account_id"},
        {"account_id": _s("Mercury account id"), "start": _s("YYYY-MM-DD"), "end": _s("YYYY-MM-DD"), "limit": {"type": "integer"}})),
    ("sol_stripe", "💳", h_stripe, _schema("sol_stripe", "Stripe, READ ONLY.",
        {"summary": "balance, MRR estimate, payouts", "balance": "raw balance", "charges": "charges", "payouts": "payouts",
         "subscriptions": "subscriptions", "balance_transactions": "balance transactions incl. fees"}, {"limit": {"type": "integer"}})),
    ("sol_xero", "📒", h_xero, _schema("sol_xero", "Xero. Read-only now; writes accept Status DRAFT only and are disabled until Phase 2.",
        {"connect_link": "Xero consent URL + redirect URI for Rick", "org": "connected organisation name only", "read": "GET an accounting endpoint", "post_draft": "Phase 2: create a DRAFT"},
        {"endpoint": _s("e.g. Accounts, Invoices?page=1, Reports/ProfitAndLoss"), "payload": {"type": "object"}})),
    ("sol_aws", "☁️", h_aws, _schema("sol_aws", "AWS Cost Explorer/Budgets, read only. One live pull per week, cached.",
        {"cost_by_month": "cost by month and service since start (default Jan 1)", "budgets": "AWS Budgets"}, {"start": _s("YYYY-MM-DD")})),
    ("sol_drive", "📁", h_drive, _schema("sol_drive", "Google Drive. Create folders/sheets in FinVerified Finance only; read Treasury; no deletes/renames.",
        {"shared_drives": "list shared drives", "list": "list a folder", "read": "read a file as text", "create_folder": "new folder", "create_sheet": "new Sheet from CSV"},
        {"folder_id": _s("folder id"), "file_id": _s("file id"), "name": _s("name"), "parent_id": _s("parent folder id"), "csv": _s("CSV text")})),
    ("sol_gmail", "✉️", h_gmail, _schema("sol_gmail", "Gmail read-only for sol@finverified.ai. Fraud-signal emails are withheld and reported.",
        {"search": "search messages", "connect_link": "one-time consent URL for Rick"}, {"query": _s("Gmail search"), "max_results": {"type": "integer"}})),
    ("sol_dm_rick", "💬", h_dm, {"name": "sol_dm_rick", "description": "Send a Slack DM to Rick (only Rick; text is PII-scrubbed).",
        "parameters": {"type": "object", "properties": {"text": _s("message")}, "required": ["text"]}}),
    ("sol_approval", "✅", h_approval, _schema("sol_approval", "Approval ledger. Approvals count only from Rick's (or Nancy's for countersign/equity) Slack ID, tied to an item ID, and void if the item changes.",
        {"propose": "register an item + payload", "record": "record an approval from the CURRENT Slack sender (pass their message text)", "check": "is item approved for this exact payload"},
        {"item_id": _s("e.g. SOL-012"), "kind": _s("general|payment|tax|countersign|equity"), "payload": {"type": "object"}, "text": _s("sender's message text")})),
    ("sol_budget", "📊", h_budget, _schema("sol_budget", "Sol's own AI spend from LiteLLM. Read-only; Sol cannot change his budget.",
        {"status": "spend, plan, safety ceiling, by-model", "check_and_notify": "send due $15/$20/$90 alerts to Rick"}, {"todo": _s("what is left to do")})),
]
