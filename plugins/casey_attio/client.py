"""Thin Attio REST v2 client for Casey. Tests monkeypatch http_json.

Read: people/companies by email, domain, name or record id, flattened to plain values.
Write: PATCH only fv_* attributes on people/companies (values normalized from the attribute type),
POST notes, POST/PATCH/GET tasks. Nothing here can delete a record, a note or a task, and nothing
can change the data model.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

API = "https://api.attio.com/v2"
OBJECTS = ("people", "companies")
_ATTR_CACHE: Dict[str, tuple] = {}
_ATTR_TTL = 3600


class PolicyError(PermissionError):
    pass


class HttpError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status


def token() -> str:
    t = os.environ.get("ATTIO_API_KEY", "").strip()
    if not t:
        raise PolicyError("ATTIO_API_KEY is not set; Attio access is not configured yet")
    return t


def http_json(method: str, url: str, *, headers: Optional[Dict[str, str]] = None, body: Optional[Any] = None,
              timeout: int = 15) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raise HttpError(e.code, e.read().decode(errors="replace"))
    return json.loads(raw.decode() or "{}")


def _call(method: str, path: str, body: Optional[Any] = None) -> Any:
    return http_json(method, API + path, headers={"Authorization": "Bearer " + token()}, body=body)


def _object(obj: str) -> str:
    o = str(obj or "").strip().lower()
    if o not in OBJECTS:
        raise PolicyError("object must be people or companies")
    return o


# --- Flattening ---------------------------------------------------------------------------------------
def _flat_value(v: Dict[str, Any]) -> Any:
    for key in ("full_name", "email_address", "domain", "currency_value", "target_record_id", "referenced_actor_id"):
        if key in v:
            if key == "target_record_id":
                return {"object": v.get("target_object"), "record_id": v[key]}
            return v[key]
    if "option" in v:
        return v["option"].get("title") if isinstance(v["option"], dict) else v["option"]
    if "status" in v:
        return v["status"].get("title") if isinstance(v["status"], dict) else v["status"]
    if "value" in v:
        return v["value"]
    if "original_phone_number" in v:
        return v["original_phone_number"]
    return v


def flatten(record: Dict[str, Any]) -> Dict[str, Any]:
    values = record.get("values") or {}
    out: Dict[str, Any] = {"record_id": (record.get("id") or {}).get("record_id"),
                           "object": (record.get("id") or {}).get("object_id")}
    for slug, vals in values.items():
        if not isinstance(vals, list) or not vals:
            continue
        flat = [_flat_value(v) for v in vals if isinstance(v, dict)]
        out[slug] = flat[0] if len(flat) == 1 else flat
    return out


# --- Reads ---------------------------------------------------------------------------------------------
def _query(obj: str, filt: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
    data = _call("POST", f"/objects/{obj}/records/query", {"filter": filt, "limit": max(1, min(int(limit), 25))})
    return [flatten(r) for r in (data.get("data") or [])]


def get_record(obj: str, record_id: str) -> Dict[str, Any]:
    obj = _object(obj)
    data = _call("GET", f"/objects/{obj}/records/{record_id}")
    return flatten(data.get("data") or {})


def find_person(email: str = "", name: str = "", limit: int = 5) -> List[Dict[str, Any]]:
    email, name = (email or "").strip().lower(), (name or "").strip()
    if email:
        return _query("people", {"email_addresses": {"email_address": {"$eq": email}}}, limit)
    if name:
        return _query("people", {"name": {"full_name": {"$contains": name}}}, limit)
    raise PolicyError("give an email or a name")


def find_company(domain: str = "", name: str = "", platform_account_id: str = "", limit: int = 5) -> List[Dict[str, Any]]:
    domain, name = (domain or "").strip().lower(), (name or "").strip()
    pid = (platform_account_id or "").strip()
    if pid:
        return _query("companies", {"fv_platform_account_id": pid}, limit)
    if domain:
        return _query("companies", {"domains": {"domain": {"$eq": domain}}}, limit)
    if name:
        return _query("companies", {"name": {"$contains": name}}, limit)
    raise PolicyError("give a domain, a name or a platform_account_id")


# --- Writes (fv_* only) ---------------------------------------------------------------------------------
def attributes(obj: str) -> Dict[str, Dict[str, Any]]:
    """slug -> {type, is_multiselect, allowed_objects} for an object, cached an hour."""
    obj = _object(obj)
    hit = _ATTR_CACHE.get(obj)
    if hit and hit[0] > time.time():
        return hit[1]
    out: Dict[str, Dict[str, Any]] = {}
    offset = 0
    while True:
        data = _call("GET", f"/objects/{obj}/attributes?limit=100&offset={offset}")
        items = data.get("data") or []
        for a in items:
            out[a.get("api_slug")] = {"type": a.get("type"), "is_multiselect": bool(a.get("is_multiselect")),
                                      "allowed_objects": [(o.get("api_slug") or o.get("object_id") or o) if isinstance(o, dict) else o
                                                          for o in ((a.get("config") or {}).get("record_reference") or {}).get("allowed_objects") or []]}
        if len(items) < 100:
            break
        offset += 100
    _ATTR_CACHE[obj] = (time.time() + _ATTR_TTL, out)
    return out


def _ref(value: Any, allowed: List[str]) -> Dict[str, str]:
    if isinstance(value, dict) and value.get("record_id"):
        return {"target_object": value.get("object") or (allowed[0] if allowed else "people"),
                "target_record_id": value["record_id"]}
    if isinstance(value, str) and ":" in value:
        o, rid = value.split(":", 1)
        return {"target_object": o.strip(), "target_record_id": rid.strip()}
    if isinstance(value, str) and allowed:
        return {"target_object": allowed[0], "target_record_id": value.strip()}
    raise PolicyError("record references need {object, record_id} or 'object:record_id'")


def normalize(obj: str, values: Dict[str, Any]) -> Dict[str, Any]:
    """Turn plain values into Attio's write shapes, allowing fv_* attributes only."""
    defs = attributes(obj)
    out: Dict[str, Any] = {}
    for slug, value in (values or {}).items():
        if not str(slug).startswith("fv_"):
            raise PolicyError(f"only fv_* fields may be written (refused: {slug})")
        d = defs.get(slug)
        if not d:
            raise PolicyError(f"unknown attribute {slug} on {obj}")
        t = d["type"]
        if value is None or value == "":
            out[slug] = []
            continue
        if t == "status":
            out[slug] = [{"status": str(value)}]
        elif t == "select":
            items = value if isinstance(value, list) else [value]
            out[slug] = [{"option": str(v)} for v in items]
        elif t == "currency":
            out[slug] = [{"currency_value": float(value)}]
        elif t == "record-reference":
            items = value if isinstance(value, list) else [value]
            out[slug] = [_ref(v, d["allowed_objects"]) for v in items]
        elif t == "rating":
            out[slug] = [{"value": int(value)}]
        elif t == "number":
            out[slug] = [{"value": float(value)}]
        elif t == "checkbox":
            out[slug] = [{"value": bool(value)}]
        else:  # text, date, timestamp
            out[slug] = [{"value": str(value)}]
    if not out:
        raise PolicyError("nothing to update")
    return out


def update_record(obj: str, record_id: str, values: Dict[str, Any]) -> Dict[str, Any]:
    obj = _object(obj)
    if not record_id:
        raise PolicyError("missing record_id")
    data = _call("PATCH", f"/objects/{obj}/records/{record_id}", {"data": {"values": normalize(obj, values)}})
    return flatten(data.get("data") or {})


def add_note(obj: str, record_id: str, title: str, content: str) -> Dict[str, Any]:
    obj = _object(obj)
    if not record_id or not str(content or "").strip():
        raise PolicyError("missing record_id or content")
    body = {"data": {"parent_object": obj, "parent_record_id": record_id, "title": (title or "Casey")[:120],
                     "format": "plaintext", "content": str(content)[:8000]}}
    data = _call("POST", "/notes", body)
    return {"note_id": ((data.get("data") or {}).get("id") or {}).get("note_id")}


def create_task(content: str, deadline: Optional[str] = None, obj: Optional[str] = None,
                record_id: Optional[str] = None) -> Dict[str, Any]:
    if not str(content or "").strip():
        raise PolicyError("missing content")
    linked = []
    if record_id:
        linked.append({"target_object": _object(obj or "people"), "target_record_id": record_id})
    assignees = []
    member = os.environ.get("ATTIO_TASK_ASSIGNEE_ID", "").strip()
    if member:
        assignees.append({"referenced_actor_type": "workspace-member", "referenced_actor_id": member})
    body = {"data": {"content": str(content)[:2000], "format": "plaintext", "deadline_at": deadline or None,
                     "is_completed": False, "linked_records": linked, "assignees": assignees}}
    data = _call("POST", "/tasks", body)
    return {"task_id": ((data.get("data") or {}).get("id") or {}).get("task_id")}


def complete_task(task_id: str) -> Dict[str, Any]:
    if not task_id:
        raise PolicyError("missing task_id")
    _call("PATCH", f"/tasks/{task_id}", {"data": {"is_completed": True}})
    return {"task_id": task_id, "completed": True}


def list_tasks(limit: int = 50, obj: Optional[str] = None, record_id: Optional[str] = None) -> List[Dict[str, Any]]:
    q = f"/tasks?limit={max(1, min(int(limit), 100))}&is_completed=false&sort=created_at%3Adesc"
    if record_id:
        q += f"&linked_object={_object(obj or 'people')}&linked_record_id={record_id}"
    data = _call("GET", q)
    out = []
    for t in data.get("data") or []:
        out.append({"task_id": (t.get("id") or {}).get("task_id"), "content": t.get("content_plaintext") or t.get("content"),
                    "deadline_at": t.get("deadline_at"), "created_at": t.get("created_at"),
                    "linked_records": [{"object": r.get("target_object"), "record_id": r.get("target_record_id")}
                                       for r in (t.get("linked_records") or [])]})
    return out
