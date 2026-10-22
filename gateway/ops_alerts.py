"""Operator alerts for fleet-hardening features (cron breaker, auth gate, budgets).

One small stdlib-only Slack poster shared by the cron circuit breaker, the
LLM auth-failure gate and the LiteLLM budget script. It deliberately does NOT
go through the agent or the gateway adapters: an alert about a broken LLM key
must still get out when the agent cannot run.

Targets live in ``config.yaml`` (non-secret); only the bot token is a secret::

    hardening:
      alerts:
        owner_user_id: "U0123ABCD"          # DM target (optional)
        channels: ["#onboarding-alerts"]    # channel names or IDs

The Slack bot token is read from ``SLACK_BOT_TOKEN``.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_CHANNELS = ["#onboarding-alerts"]
_SLACK_POST_URL = "https://slack.com/api/chat.postMessage"


def _alert_config() -> Dict[str, Any]:
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
    except Exception:
        return {}
    hardening = cfg.get("hardening") if isinstance(cfg, dict) else None
    alerts = (hardening or {}).get("alerts") if isinstance(hardening, dict) else None
    return alerts if isinstance(alerts, dict) else {}


def resolve_targets(
    owner_user_id: Optional[str] = None, channels: Optional[List[str]] = None
) -> List[str]:
    """Return the ordered, de-duplicated Slack targets (owner DM first)."""
    cfg = _alert_config()
    owner = owner_user_id if owner_user_id is not None else cfg.get("owner_user_id")
    chans = channels if channels is not None else cfg.get("channels")
    if not chans:
        chans = DEFAULT_CHANNELS
    targets: List[str] = []
    for t in [owner, *chans]:
        t = str(t or "").strip()
        if t and t not in targets:
            targets.append(t)
    return targets


def post_slack_alert(
    text: str,
    *,
    targets: Optional[List[str]] = None,
    token: Optional[str] = None,
    timeout: float = 10.0,
) -> bool:
    """Post ``text`` to every alert target. True if at least one post landed.

    Never raises: alerting must not break the code path that is already
    handling a failure.
    """
    token = token or os.environ.get("SLACK_BOT_TOKEN", "")
    if not token:
        logger.warning("ops alert not sent: SLACK_BOT_TOKEN is not set")
        return False
    sent = False
    for target in targets if targets is not None else resolve_targets():
        body = json.dumps({"channel": target, "text": text}).encode()
        req = urllib.request.Request(
            _SLACK_POST_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read() or b"{}")
        except Exception as exc:
            logger.warning("ops alert to %s failed: %s", target, type(exc).__name__)
            continue
        if payload.get("ok"):
            sent = True
        else:
            logger.warning("ops alert to %s rejected: %s", target, payload.get("error"))
    return sent
