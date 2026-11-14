"""Casey (Partner & Customer Success) Google plugin: her OWN mailbox and calendar only
(CASEY_OWN_ACCOUNT, default casey@finverified.ai). See deploy/casey/AGENTS.md."""

from __future__ import annotations


def register(ctx) -> None:
    from . import server, tools

    for name, emoji, handler, schema in tools.TOOLS:
        ctx.register_tool(name=name, toolset="casey_google", schema=schema, handler=handler, emoji=emoji,
                          check_fn=tools.check_requirements, requires_env=list(tools._REQUIRED_ENV))
    server.start()
