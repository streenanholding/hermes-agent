"""Gateway LLM health loop: 5-minute LiteLLM probe, queue replay, Better Stack heartbeat.

* Every ``HEALTH_INTERVAL_SECONDS`` (5 min) one tiny LiteLLM call runs. While
  the auth gate is blocked, the first success reopens it and the held requests
  are replayed through their original adapters.
* Every ``HEARTBEAT_INTERVAL_SECONDS`` (10 min) the agent pings the Better
  Stack heartbeat URL in ``BETTERSTACK_HEARTBEAT_URL`` — but ONLY if the last
  health check succeeded and is recent. A broken key therefore goes quiet and
  Better Stack's missed-heartbeat alert fires. An empty/unset URL disables the
  ping (Rick sets the value in Railway).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import urllib.request
from typing import Any, Awaitable, Callable, Optional

from gateway.auth_gate import HEALTH_INTERVAL_SECONDS, AuthFailureGate, get_gate

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 600
HEARTBEAT_ENV = "BETTERSTACK_HEARTBEAT_URL"


def heartbeat_due_ok(gate: AuthFailureGate, now: Optional[float] = None) -> bool:
    """True when the last health check succeeded and is fresh enough to trust."""
    if gate.last_health_ok is not True or gate.last_health_at is None:
        return False
    now = time.monotonic() if now is None else now
    return (now - gate.last_health_at) <= 2 * HEALTH_INTERVAL_SECONDS


def ping_heartbeat(url: Optional[str] = None, timeout: float = 10.0) -> bool:
    url = (os.environ.get(HEARTBEAT_ENV, "") if url is None else url).strip()
    if not url:
        return False
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception as exc:
        logger.warning("Better Stack heartbeat ping failed: %s", type(exc).__name__)
        return False


async def health_tick(
    gate: AuthFailureGate,
    replay: Callable[[Any], Awaitable[None]],
    *,
    probe: Optional[Callable[[], bool]] = None,
) -> None:
    """One 5-minute tick: recover the gate if blocked, else record routine health."""
    loop = asyncio.get_running_loop()
    if gate.blocked:
        drained = await loop.run_in_executor(None, lambda: gate.check_health(force=True))
        for item in drained or []:
            try:
                await replay(item)
            except Exception:
                logger.warning("replay of held request failed", exc_info=True)
        return
    ok = await loop.run_in_executor(None, probe or gate._probe)
    gate.record_health(bool(ok))


async def run_health_loop(
    replay: Callable[[Any], Awaitable[None]],
    gate: Optional[AuthFailureGate] = None,
    *,
    health_interval: float = HEALTH_INTERVAL_SECONDS,
    heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS,
) -> None:
    gate = gate or get_gate()
    loop = asyncio.get_running_loop()
    next_heartbeat = time.monotonic() + heartbeat_interval
    while True:
        try:
            await health_tick(gate, replay)
            if time.monotonic() >= next_heartbeat:
                next_heartbeat += heartbeat_interval
                if heartbeat_due_ok(gate):
                    await loop.run_in_executor(None, ping_heartbeat)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("health loop tick failed", exc_info=True)
        await asyncio.sleep(health_interval)
