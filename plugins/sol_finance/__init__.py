"""Sol (FinVerified finance agent) plugin. Tools, guards and schedules; see deploy/sol/AGENTS.md."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

from . import pii

logger = logging.getLogger(__name__)

# Tools whose string args are persisted (memory, files, todos): scrub before they run.
_PERSISTING = ("memory", "write_file", "patch", "todo")


def _pre_tool_call(tool_name: str = "", args: Dict[str, Any] = None, **_kw):
    if not any(tool_name.startswith(p) or tool_name == p for p in _PERSISTING):
        return None
    scrubbed = pii.scrub_obj(args or {})
    if scrubbed != (args or {}):
        return {"action": "modify", "args": scrubbed}
    return None


def register(ctx) -> None:
    from . import schedules, server, tools

    pii.install_log_filter()
    for name, emoji, handler, schema in tools.TOOLS:
        ctx.register_tool(name=name, toolset="sol_finance", schema=schema, handler=handler, emoji=emoji)
    ctx.register_hook("pre_tool_call", _pre_tool_call)
    if os.environ.get("HERMES_AGENT_DEPLOY") == "sol":
        server.start()
        try:
            schedules.ensure_jobs()
        except Exception:
            logger.exception("sol schedule seeding failed")
