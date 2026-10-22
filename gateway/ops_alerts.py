"""Quiet-by-default operator messaging shared by every agent.

Rules (deploy/common/REPORTING.md):

* Routine events (job ran, job done, a failure that self-handled) go to the
  Slack channel ``#agent-log`` as ONE line each, never in a thread.
* Rick is DM'd only for a decision or credential he must supply. If three or
  more such messages pile up inside one flush window they go out as a single
  bundled DM, never three.
* The same failure is never posted twice: every post carries a dedupe ``key``
  and a key that has already been posted is dropped until ``clear_key``.

Slack calls are injectable (``_send``) so the logic is testable offline.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

LOG_CHANNEL_ENV = "AGENT_LOG_CHANNEL"
DEFAULT_LOG_CHANNEL = "#agent-log"
RICK_ID_ENVS = ("RICK_SLACK_USER_ID", "SOL_RICK_SLACK_ID")
BUNDLE_AT = 3

_lock = threading.Lock()
_posted: Set[str] = set()
_pending: List[Tuple[Optional[str], str]] = []


def _slack(method: str, body: Dict[str, Any], token: str) -> Dict[str, Any]:
    req = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read() or b"{}")


def _one_line(text: str) -> str:
    return " ".join(str(text).split())


def _rick_id() -> str:
    for name in RICK_ID_ENVS:
        if os.environ.get(name):
            return os.environ[name]
    return ""


def _send_channel(text: str) -> bool:
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    if not token:
        return False
    channel = os.environ.get(LOG_CHANNEL_ENV, DEFAULT_LOG_CHANNEL)
    return bool(_slack("chat.postMessage", {"channel": channel, "text": text}, token).get("ok"))


def _send_dm(text: str) -> bool:
    token, rick = os.environ.get("SLACK_BOT_TOKEN", ""), _rick_id()
    if not (token and rick):
        return False
    opened = _slack("conversations.open", {"users": rick}, token)
    channel = (opened.get("channel") or {}).get("id")
    return bool(channel) and bool(_slack("chat.postMessage", {"channel": channel, "text": text}, token).get("ok"))


def _claim(key: Optional[str]) -> bool:
    """True if this key has not been posted yet (and claims it)."""
    if key is None:
        return True
    with _lock:
        if key in _posted:
            return False
        _posted.add(key)
        return True


def clear_key(key: str) -> None:
    """Allow ``key`` to post again (call when the underlying failure recovers)."""
    with _lock:
        _posted.discard(key)


def post_agent_log(text: str, key: Optional[str] = None, *, _send: Optional[Callable[[str], bool]] = None) -> bool:
    """One line to #agent-log. Returns True if it was sent."""
    if not _claim(key):
        return False
    try:
        ok = bool((_send or _send_channel)(_one_line(text)))
    except Exception:
        logger.warning("agent-log post failed", exc_info=True)
        ok = False
    if not ok and key is not None:
        clear_key(key)
    return ok


def notify_rick(text: str, key: Optional[str] = None) -> bool:
    """Queue a decision/credential request for Rick. Sent by ``flush_pending``.

    Returns False when it was dropped as a duplicate.
    """
    if not _claim(key):
        return False
    with _lock:
        _pending.append((key, text.strip()))
    return True


def flush_pending(*, _send: Optional[Callable[[str], bool]] = None) -> int:
    """Send queued DMs to Rick: one message, bundled when BUNDLE_AT or more.

    Returns the number of DMs sent (0 or 1 for a bundle, else one per item
    when there are fewer than BUNDLE_AT). A failed send re-queues the items
    and releases their dedupe keys so nothing is lost or double-posted.
    """
    send = _send or _send_dm
    with _lock:
        batch, _pending[:] = list(_pending), []
    if not batch:
        return 0
    if len(batch) >= BUNDLE_AT:
        messages = [f"{len(batch)} items need you:\n" + "\n".join(f"{i}. {t}" for i, (_, t) in enumerate(batch, 1))]
    else:
        messages = [t for _, t in batch]
    sent = 0
    for msg in messages:
        try:
            if not send(msg):
                raise RuntimeError("slack DM not delivered")
            sent += 1
        except Exception:
            logger.warning("DM to Rick failed; re-queued", exc_info=True)
            with _lock:
                _pending[:0] = batch
                for key, _ in batch:
                    if key is not None:
                        _posted.discard(key)
            return sent
    return sent


def log_job_result(job: Dict[str, Any], success: bool, error: Optional[str] = None) -> None:
    """One #agent-log line per job event. A failure posts once until the job next succeeds."""
    name = job.get("name") or job.get("id") or "cron job"
    key = f"job-fail:{job.get('id') or name}"
    if success:
        clear_key(key)
        post_agent_log(f"✅ {name} ran")
    else:
        post_agent_log(f"⚠️ {name} failed: {_one_line(error or 'unknown error')[:200]}", key=key)


def post_slack_alert(text: str, key: Optional[str] = None) -> bool:
    """Compat name used by the breaker/auth gate: a one-line #agent-log post."""
    return post_agent_log(text, key=key)


def reset_for_tests() -> None:
    with _lock:
        _posted.clear()
        _pending.clear()
