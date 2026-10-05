"""Slack DMs to Rick. Every outgoing message is PII-scrubbed."""

from __future__ import annotations

import os
from typing import Any, Dict

from . import approvals, common, pii


def dm(user_id: str, text: str) -> Dict[str, Any]:
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    if not token or not user_id:
        return {"ok": False, "error": "missing SLACK_BOT_TOKEN or recipient"}
    hdr = {"Authorization": f"Bearer {token}"}
    opened = common.http_json("POST", "https://slack.com/api/conversations.open", headers=hdr,
                              body={"users": user_id})
    channel = (opened.get("channel") or {}).get("id")
    if not channel:
        return {"ok": False, "error": opened.get("error", "conversations.open failed")}
    sent = common.http_json("POST", "https://slack.com/api/chat.postMessage", headers=hdr,
                            body={"channel": channel, "text": pii.scrub(text)})
    return {"ok": bool(sent.get("ok")), "error": sent.get("error")}


def dm_rick(text: str) -> Dict[str, Any]:
    """DMs go to Rick's ID only. No model-supplied recipient is accepted."""
    return dm(approvals.rick_id(), text)
