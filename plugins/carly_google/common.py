"""Shared helpers: state dir, config, tiny HTTP client. Tests monkeypatch http_bytes / http_json."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


class PolicyError(PermissionError):
    """A request the plugin refuses on purpose (outside Carly's remit)."""


class HttpError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status


def home() -> Path:
    return Path(os.environ.get("HERMES_HOME", "/opt/data"))


def state_dir() -> Path:
    d = home() / "carly"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_state(name: str, default: Any) -> Any:
    try:
        return json.loads((state_dir() / name).read_text())
    except Exception:
        return default


def save_state(name: str, data: Any) -> None:
    p = state_dir() / name
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def carly_config() -> Dict[str, Any]:
    """The ``carly:`` section of config.yaml (policy switches, never secrets)."""
    try:
        from hermes_cli.config import load_config  # type: ignore

        return (load_config() or {}).get("carly", {}) or {}
    except Exception:
        return {}


def mailbox() -> str:
    """The one mailbox this agent signs in as. Never hard-coded."""
    email = os.environ.get("CARLY_EMAIL", "").strip()
    if not email:
        raise PolicyError("CARLY_EMAIL is not set; Google access is not configured yet")
    return email


def env_required(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise PolicyError(f"{name} is not set; this part of Google access is not configured yet")
    return val


def http_bytes(method: str, url: str, *, headers: Optional[Dict[str, str]] = None,
               data: Optional[bytes] = None, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, data=data, method=method, headers=dict(headers or {}))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise HttpError(e.code, e.read().decode(errors="replace"))


def http_json(method: str, url: str, *, headers: Optional[Dict[str, str]] = None,
              body: Optional[Any] = None, form: Optional[Dict[str, str]] = None,
              timeout: int = 30) -> Any:
    data = None
    hdrs = dict(headers or {})
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif body is not None:
        data = json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    raw = http_bytes(method, url, headers=hdrs, data=data, timeout=timeout)
    return json.loads(raw.decode() or "{}")
