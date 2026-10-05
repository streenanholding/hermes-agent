"""Shared helpers: state dir, tiny HTTP client, config."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


def home() -> Path:
    return Path(os.environ.get("HERMES_HOME", "/opt/data"))


def state_dir() -> Path:
    d = home() / "sol"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_state(name: str, default: Any) -> Any:
    p = state_dir() / name
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def save_state(name: str, data: Any) -> None:
    p = state_dir() / name
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    os.replace(tmp, p)


def sol_config() -> Dict[str, Any]:
    try:
        from hermes_cli.config import load_config  # type: ignore

        return (load_config() or {}).get("sol", {}) or {}
    except Exception:
        return {}


class HttpError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status


def http_json(method: str, url: str, *, headers: Optional[Dict[str, str]] = None,
              body: Optional[Any] = None, form: Optional[Dict[str, str]] = None,
              timeout: int = 30) -> Any:
    """One HTTP call returning parsed JSON. Tests monkeypatch this function."""
    data = None
    hdrs = dict(headers or {})
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif body is not None:
        data = json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode() or "{}"
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        raise HttpError(e.code, e.read().decode(errors="replace"))
