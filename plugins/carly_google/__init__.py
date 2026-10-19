"""Carly (FinVerified chief of staff) Google plugin: Gmail, Calendar, Drive for CARLY_EMAIL. See deploy/carly/AGENTS.md."""

from __future__ import annotations


def register(ctx) -> None:
    from . import server, tools

    for name, emoji, handler, schema in tools.TOOLS:
        ctx.register_tool(name=name, toolset="carly_google", schema=schema, handler=handler, emoji=emoji,
                          check_fn=tools.check_requirements, requires_env=list(tools._REQUIRED_ENV))
    server.start()
