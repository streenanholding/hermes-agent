"""LLM provider-auth failure gate: alert once, hold requests, replay on recovery.

When the LLM gateway (LiteLLM) answers 401/403 or a budget/expiry error, every
further request would fail the same way and each retry just adds noise (and
load on a key that may be rate-protected). Instead:

1. ``trip()`` flips the gate to blocked and posts ONE "AI key problem" alert.
2. While blocked, the gateway ``hold()``s incoming messages in a queue
   instead of running the agent.
3. A health check (a tiny LiteLLM call) runs every ``HEALTH_INTERVAL_SECONDS``
   (5 minutes). The first success reopens the gate and ``drain()`` hands the
   queued requests back for replay, oldest first.

The gate is process-wide state; ``probe``/``alert``/``replay`` are injectable
so the logic is testable without a network. Health results also feed the
per-agent Better Stack heartbeat (see ``gateway/health_loop.py``).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.request
from collections import deque
from typing import Any, Callable, Deque, List, Optional

logger = logging.getLogger(__name__)

HEALTH_INTERVAL_SECONDS = 300
MAX_QUEUE = 500
ALERT_TEXT = "🔑 AI key problem — all tasks blocked"

_BUDGET_MARKERS = (
    "budget has been exceeded",
    "budget_exceeded",
    "exceeded budget",
    "max budget",
    "key expired",
    "expired key",
    "api key expired",
    "key is expired",
)


def is_auth_or_budget_failure(status_code: Optional[int], message: str = "") -> bool:
    """401/403 or a LiteLLM budget/expiry error (which LiteLLM sends as 400/401)."""
    if status_code in (401, 403):
        return True
    text = (message or "").lower()
    return any(m in text for m in _BUDGET_MARKERS)


def _model_config() -> dict:
    try:
        from hermes_cli.config import load_config

        model = (load_config() or {}).get("model")
    except Exception:
        return {}
    return model if isinstance(model, dict) else {}


def litellm_health_probe(
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    timeout: float = 20.0,
) -> bool:
    """One tiny chat completion against the LiteLLM gateway. True iff HTTP 2xx.

    Uses the agent's own inference settings so it exercises the same virtual
    key and route: ``model.base_url`` / ``model.default`` from config.yaml
    and the ``OPENAI_API_KEY``
    secret.
    """
    cfg = _model_config()
    base = (base_url or cfg.get("base_url") or os.environ.get("OPENAI_BASE_URL") or "").rstrip("/")
    key = api_key or os.environ.get("OPENAI_API_KEY") or ""
    mdl = model or cfg.get("default") or ""
    if not (base and key and mdl):
        logger.warning("LiteLLM health probe not configured (base url / key / model)")
        return False
    body = json.dumps(
        {"model": mdl, "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]}
    ).encode()
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception as exc:
        logger.info("LiteLLM health probe failed: %s", type(exc).__name__)
        return False


class AuthFailureGate:
    def __init__(
        self,
        *,
        probe: Callable[[], bool] = litellm_health_probe,
        alert: Optional[Callable[[str], Any]] = None,
        clock: Callable[[], float] = time.monotonic,
        interval: float = HEALTH_INTERVAL_SECONDS,
        max_queue: int = MAX_QUEUE,
    ):
        self._probe = probe
        self._alert = alert
        self._clock = clock
        self._interval = interval
        self._lock = threading.Lock()
        self._blocked = False
        self._queue: Deque[Any] = deque(maxlen=max_queue)
        self._next_check = 0.0
        self.last_health_ok: Optional[bool] = None
        self.last_health_at: Optional[float] = None
        self.blocked_reason = ""
        self._outage = 0

    # ── state ───────────────────────────────────────────────────────────
    @property
    def blocked(self) -> bool:
        return self._blocked

    def queued(self) -> int:
        return len(self._queue)

    def _send_alert(self, text: str, *, routine: bool = False) -> None:
        try:
            if self._alert is not None:
                self._alert(text)
            else:
                from gateway import ops_alerts

                if routine:
                    ops_alerts.post_agent_log(text)
                else:
                    # A dead key needs Rick (credential): one deduped DM per outage.
                    ops_alerts.notify_rick(text, key=f"auth-gate:{self._outage}")
        except Exception:
            logger.warning("auth gate alert failed", exc_info=True)

    # ── trip / hold ─────────────────────────────────────────────────────
    def trip(self, reason: str = "") -> bool:
        """Block the gate. Alerts exactly once per outage. True if newly tripped."""
        with self._lock:
            if self._blocked:
                return False
            self._blocked = True
            self._outage += 1
            self.blocked_reason = reason
            self.last_health_ok = False
            self._next_check = self._clock() + self._interval
        detail = f"\nProvider said: {' '.join(reason.split())[:200]}" if reason else ""
        self._send_alert(
            f"{ALERT_TEXT}.{detail}\nRequests are being held and will replay "
            "automatically once the 5-minute health check passes."
        )
        return True

    def hold(self, item: Any) -> bool:
        """Queue ``item`` if blocked. False means the gate is open: run it now."""
        with self._lock:
            if not self._blocked:
                return False
            self._queue.append(item)
            return True

    # ── health check / recovery ─────────────────────────────────────────
    def check_health(self, *, force: bool = False) -> Optional[List[Any]]:
        """Run the probe if due. Returns drained queue on recovery, else None."""
        now = self._clock()
        with self._lock:
            if not self._blocked or (not force and now < self._next_check):
                return None
            self._next_check = now + self._interval
        ok = bool(self._probe())
        self.last_health_ok = ok
        self.last_health_at = now
        if not ok:
            return None
        with self._lock:
            self._blocked = False
            self.blocked_reason = ""
            drained = list(self._queue)
            self._queue.clear()
        self._send_alert(
            f"✅ AI key healthy again. Replaying {len(drained)} held request(s).",
            routine=True,
        )
        return drained

    def record_health(self, ok: bool) -> None:
        """Record a routine probe result while the gate is open.

        A single failed probe does not trip the gate (could be a blip, and the
        agent's own request path trips it on a real 401/403); it only stops
        the Better Stack heartbeat until a probe succeeds again.
        """
        self.last_health_ok = ok
        self.last_health_at = self._clock()


_gate: Optional[AuthFailureGate] = None


def get_gate() -> AuthFailureGate:
    global _gate
    if _gate is None:
        _gate = AuthFailureGate()
    return _gate


def reset_gate_for_tests(gate: Optional[AuthFailureGate] = None) -> None:
    global _gate
    _gate = gate
