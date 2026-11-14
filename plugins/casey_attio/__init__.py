"""casey_attio plugin: Casey's CRM tools over Attio REST v2 (FinVerified workspace).

Tools: attio_find_person, attio_find_company, attio_get_record, attio_update_record (fv_* only),
attio_add_note, attio_create_task, attio_complete_task, attio_my_tasks. No delete anywhere.
Identity and scope come from ATTIO_API_KEY (the per-agent 'casey-attio' token, FIN-264).
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict

from . import client

_REQUIRED_ENV = ("ATTIO_API_KEY",)


def check_requirements() -> bool:
    return all(os.environ.get(k) for k in _REQUIRED_ENV)


def _run(fn: Callable[[], Any]) -> str:
    try:
        res = fn()
        if isinstance(res, dict):
            return json.dumps({"success": True, **res}, default=str)
        return json.dumps({"success": True, "data": res}, default=str)
    except Exception as e:
        return json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"})


def _s(desc: str) -> Dict[str, Any]:
    return {"type": "string", "description": desc}


def h_find_person(args, **_):
    return _run(lambda: {"people": client.find_person(args.get("email", ""), args.get("name", ""), args.get("limit", 5))})


def h_find_company(args, **_):
    return _run(lambda: {"companies": client.find_company(args.get("domain", ""), args.get("name", ""),
                                                          args.get("platform_account_id", ""), args.get("limit", 5))})


def h_get_record(args, **_):
    return _run(lambda: {"record": client.get_record(args.get("object", ""), args.get("record_id", ""))})


def h_update_record(args, **_):
    return _run(lambda: {"record": client.update_record(args.get("object", ""), args.get("record_id", ""),
                                                        args.get("values") or {})})


def h_add_note(args, **_):
    return _run(lambda: client.add_note(args.get("object", ""), args.get("record_id", ""), args.get("title", ""),
                                        args.get("content", "")))


def h_create_task(args, **_):
    return _run(lambda: client.create_task(args.get("content", ""), args.get("deadline"), args.get("object"),
                                           args.get("record_id")))


def h_complete_task(args, **_):
    return _run(lambda: client.complete_task(args.get("task_id", "")))


def h_my_tasks(args, **_):
    return _run(lambda: {"tasks": client.list_tasks(args.get("limit", 50), args.get("object"), args.get("record_id"))})


_REC = {"object": {"type": "string", "enum": ["people", "companies"]}, "record_id": _s("Attio record id (UUID)")}

TOOLS = [
    ("attio_find_person", "🔎", h_find_person, {
        "name": "attio_find_person",
        "description": "Find people in Attio by email (exact) or name (contains). Returns their FinVerified fields "
                       "(fv_role, fv_partner_status, fv_partner_track, fv_active_practices, commission, next action ...). "
                       "Do this before discussing anyone's account.",
        "parameters": {"type": "object", "properties": {"email": _s("email address"), "name": _s("full or partial name"),
                                                        "limit": {"type": "integer"}}}}),
    ("attio_find_company", "🏥", h_find_company, {
        "name": "attio_find_company",
        "description": "Find clinics, DSOs, partner orgs or integration partners in Attio by domain, name or the platform "
                       "account id. Returns lifecycle stage, subscription, locations, MRR, health, Pathway Partner, next action.",
        "parameters": {"type": "object", "properties": {"domain": _s("website domain"), "name": _s("company name"),
                                                        "platform_account_id": _s("FinVerified platform account id"),
                                                        "limit": {"type": "integer"}}}}),
    ("attio_get_record", "📇", h_get_record, {
        "name": "attio_get_record",
        "description": "Read one person or company by record id, with every field flattened.",
        "parameters": {"type": "object", "required": ["object", "record_id"], "properties": _REC}}),
    ("attio_update_record", "✏️", h_update_record, {
        "name": "attio_update_record",
        "description": "Update FinVerified fields (fv_* only) on a person or company: e.g. fv_next_action, fv_next_action_due "
                       "(YYYY-MM-DD), fv_last_support_contact_at (ISO timestamp), fv_health_flags, fv_churn_reason. "
                       "Plain values; statuses and selects by title. Never changes lifecycle or partner status "
                       "that the platform owns unless Rick or Kirk asked for the correction.",
        "parameters": {"type": "object", "required": ["object", "record_id", "values"], "properties": {
            **_REC, "values": {"type": "object", "description": "fv_* slug -> value"}}}}),
    ("attio_add_note", "📝", h_add_note, {
        "name": "attio_add_note",
        "description": "Add a plain-text note to a person or company: what was said, what you did, what is next. "
                       "One note per interaction. Never include patient details.",
        "parameters": {"type": "object", "required": ["object", "record_id", "content"], "properties": {
            **_REC, "title": _s("short title, e.g. 'Call 11/20 — onboarding stall'"), "content": _s("the note")}}}),
    ("attio_create_task", "✅", h_create_task, {
        "name": "attio_create_task",
        "description": "Create a task (yours or a handoff) optionally linked to a person or company, with a deadline.",
        "parameters": {"type": "object", "required": ["content"], "properties": {
            "content": _s("what to do, who, by when"), "deadline": _s("ISO timestamp, e.g. 2026-11-21T14:00:00Z"),
            "object": {"type": "string", "enum": ["people", "companies"]}, "record_id": _s("linked record id")}}}),
    ("attio_complete_task", "☑️", h_complete_task, {
        "name": "attio_complete_task",
        "description": "Mark a task complete after you did it and logged the outcome.",
        "parameters": {"type": "object", "required": ["task_id"], "properties": {"task_id": _s("task id")}}}),
    ("attio_my_tasks", "📋", h_my_tasks, {
        "name": "attio_my_tasks",
        "description": "List open tasks (newest first), optionally only those linked to one record. Work them in the "
                       "every-15-minutes routine; complete each one after logging the outcome.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer"},
                                                        "object": {"type": "string", "enum": ["people", "companies"]},
                                                        "record_id": _s("only tasks linked to this record")}}}),
]


def register(ctx) -> None:
    for name, emoji, handler, schema in TOOLS:
        ctx.register_tool(name=name, toolset="casey_attio", schema=schema, handler=handler, emoji=emoji,
                          check_fn=check_requirements, requires_env=list(_REQUIRED_ENV))
