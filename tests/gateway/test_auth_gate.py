"""LLM auth-failure gate: one alert, hold requests, replay after health check.

Contract:
- 401/403 and LiteLLM budget/expiry errors are recognised; ordinary errors aren't.
- trip() alerts exactly once per outage no matter how many requests fail.
- While blocked, requests are held (not run); while open they're not.
- The health check runs at most every 5 minutes; a failing probe keeps the
  queue; the first passing probe reopens the gate and returns the queue FIFO.
- Heartbeat pings only when the last health check succeeded and is fresh.
"""

import asyncio

import pytest

from gateway import health_loop
from gateway.auth_gate import (
    ALERT_TEXT,
    AuthFailureGate,
    is_auth_or_budget_failure,
)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make_gate(probe_results, clock=None):
    clock = clock or Clock()
    alerts, probes = [], []
    results = iter(probe_results)

    def probe():
        probes.append(clock.t)
        return next(results)

    gate = AuthFailureGate(probe=probe, alert=alerts.append, clock=clock, interval=300)
    return gate, alerts, probes, clock


@pytest.mark.parametrize(
    "status,msg,expected",
    [
        (401, "", True),
        (403, "forbidden", True),
        (400, "Budget has been exceeded! Current cost: 10, Max budget: 10", True),
        (401, "key expired", True),
        (400, "key is expired", True),
        (429, "rate limit", False),
        (500, "internal error", False),
        (400, "context length exceeded", False),
    ],
)
def test_failure_classification(status, msg, expected):
    assert is_auth_or_budget_failure(status, msg) is expected


def test_trip_alerts_exactly_once_per_outage():
    gate, alerts, *_ = make_gate([])
    assert gate.trip("401 invalid key") is True
    assert gate.trip("401 invalid key") is False
    assert gate.trip("403") is False
    assert len(alerts) == 1
    assert ALERT_TEXT in alerts[0] and "401 invalid key" in alerts[0]


def test_requests_held_only_while_blocked():
    gate, *_ = make_gate([])
    assert gate.hold("early") is False  # open: caller runs it
    gate.trip("401")
    assert gate.hold("a") is True and gate.hold("b") is True
    assert gate.queued() == 2


def test_health_check_waits_five_minutes_and_keeps_queue_on_failure():
    gate, alerts, probes, clock = make_gate([False, True])
    gate.trip("401")
    gate.hold("a")

    assert gate.check_health() is None and probes == []  # not due yet
    clock.t += 300
    assert gate.check_health() is None and len(probes) == 1  # probe failed
    assert gate.blocked and gate.queued() == 1 and gate.last_health_ok is False
    assert gate.check_health() is None and len(probes) == 1  # throttled again

    clock.t += 300
    assert gate.check_health() == ["a"]  # probe passed -> replay list
    assert not gate.blocked and gate.queued() == 0


def test_recovery_replays_fifo_and_alerts_recovery_once():
    gate, alerts, _, clock = make_gate([True])
    gate.trip("403")
    for item in ("m1", "m2", "m3"):
        gate.hold(item)
    clock.t += 300
    assert gate.check_health() == ["m1", "m2", "m3"]
    assert len(alerts) == 2 and "healthy again" in alerts[1] and "3" in alerts[1]
    assert gate.check_health(force=True) is None  # open gate: nothing to do


def test_queue_is_bounded():
    gate = AuthFailureGate(probe=lambda: True, alert=lambda t: None, max_queue=2)
    gate.trip("401")
    for i in range(4):
        gate.hold(i)
    assert gate.queued() == 2


def test_health_tick_replays_held_requests_on_recovery():
    gate, _, _, clock = make_gate([True])
    gate.trip("401")
    gate.hold("x"), gate.hold("y")
    replayed = []

    async def replay(item):
        replayed.append(item)

    asyncio.run(health_loop.health_tick(gate, replay))
    assert replayed == ["x", "y"] and not gate.blocked


def test_health_tick_failed_probe_while_open_does_not_trip():
    gate, alerts, *_ = make_gate([False])

    async def replay(item):  # pragma: no cover - nothing queued
        raise AssertionError

    asyncio.run(health_loop.health_tick(gate, replay))
    assert gate.last_health_ok is False and not gate.blocked and alerts == []


def test_heartbeat_requires_fresh_successful_health_check():
    gate, _, _, clock = make_gate([])
    assert health_loop.heartbeat_due_ok(gate, clock()) is False  # never checked
    gate.record_health(True)
    assert health_loop.heartbeat_due_ok(gate, clock()) is True
    assert health_loop.heartbeat_due_ok(gate, clock() + 601) is False  # stale
    gate.record_health(False)
    assert health_loop.heartbeat_due_ok(gate, clock()) is False


def test_ping_heartbeat_is_noop_when_url_unset(monkeypatch):
    monkeypatch.delenv(health_loop.HEARTBEAT_ENV, raising=False)
    called = []
    monkeypatch.setattr(health_loop.urllib.request, "urlopen", lambda *a, **k: called.append(a))
    assert health_loop.ping_heartbeat() is False
    monkeypatch.setenv(health_loop.HEARTBEAT_ENV, "   ")
    assert health_loop.ping_heartbeat() is False
    assert called == []


def test_ping_heartbeat_hits_configured_url(monkeypatch):
    seen = []

    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setenv(health_loop.HEARTBEAT_ENV, "https://uptime.betterstack.com/api/v1/heartbeat/abc")
    monkeypatch.setattr(health_loop.urllib.request, "urlopen", lambda url, timeout=0: seen.append(url) or Resp())
    assert health_loop.ping_heartbeat() is True
    assert seen == ["https://uptime.betterstack.com/api/v1/heartbeat/abc"]
