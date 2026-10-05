"""gateway:startup hook for Sol. Idempotent; never blocks the gateway."""

import logging

logger = logging.getLogger("sol.startup")


async def handle(event_type, context):
    try:
        from hermes_cli.plugins import discover_plugins

        discover_plugins()
        from plugins.sol_finance import pii, schedules, server

        pii.install_log_filter()
        server.start()
        schedules.ensure_jobs()
        logger.warning("sol startup: callback server started=%s, schedules ensured", server._started)
    except Exception:
        logger.exception("sol startup hook failed")
