"""Provider-auth gate: alert once, queue work, replay on a healthy 5-minute check."""

import asyncio

from gateway import auth_gate, health_loop
from gateway.auth_gate import AuthFailureGate, is_auth_or_budget_failure


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _gate(probe_results, alerts=None):
    results = list(probe_results)
    clock = Clock()
    alerts = alerts if alerts is not None else []
    gate = AuthFailureGate(probe=lambda: results.pop(0), alert=alerts.append, clock=clock)
    return gate, clock, alerts


def test_classifies_auth_and_budget_errors():
    assert is_auth_or_budget_failure(401) and is_auth_or_budget_failure(403)
    assert is_auth_or_budget_failure(400, "Budget has been exceeded! Current cost: 20")
    assert is_auth_or_budget_failure(None, "API key expired")
    assert not is_auth_or_budget_failure(500, "upstream timeout")


def test_trip_alerts_exactly_once_per_outage():
    gate, _, alerts = _gate([])
    assert gate.trip("401 invalid key") is True
    assert gate.trip("401 invalid key") is False and gate.trip("again") is False
    assert len(alerts) == 1 and "AI key problem" in alerts[0]


def test_open_gate_does_not_hold():
    gate, _, _ = _gate([])
    assert gate.hold("msg") is False and gate.queued() == 0


def test_blocked_gate_queues_and_replays_in_order_on_recovery():
    gate, clock, alerts = _gate([False, True])
    gate.trip("403")
    for m in ("a", "b", "c"):
        assert gate.hold(m) is True
    clock.t += 301
    assert gate.check_health() is None and gate.blocked and gate.queued() == 3  # still dead
    clock.t += 301
    assert gate.check_health() == ["a", "b", "c"]
    assert not gate.blocked and gate.queued() == 0
    assert "healthy again" in alerts[-1] and "3" in alerts[-1]


def test_health_check_waits_five_minutes_between_probes():
    gate, clock, _ = _gate([True])
    gate.trip("403")
    clock.t += 100
    assert gate.check_health() is None  # not due: probe not consumed
    clock.t += 201
    assert gate.check_health() == []


def test_queue_is_bounded():
    gate = AuthFailureGate(probe=lambda: False, alert=lambda t: None, max_queue=2)
    gate.trip("403")
    for m in ("a", "b", "c"):
        gate.hold(m)
    assert gate.queued() == 2


def test_second_outage_alerts_again():
    gate, clock, alerts = _gate([True])
    gate.trip("403")
    clock.t += 301
    gate.check_health()
    gate.trip("403 again")
    assert len(alerts) == 3  # outage 1 alert, recovery, outage 2 alert


def test_health_tick_replays_held_requests():
    gate, _, _ = _gate([True])
    gate.trip("403")
    gate.hold("x"), gate.hold("y")
    replayed = []

    async def replay(item):
        replayed.append(item)

    asyncio.run(health_loop.health_tick(gate, replay))
    assert replayed == ["x", "y"] and not gate.blocked


def test_health_tick_records_routine_health_when_open():
    gate, _, _ = _gate([])
    asyncio.run(health_loop.health_tick(gate, lambda i: None, probe=lambda: True))
    assert gate.last_health_ok is True


def test_heartbeat_only_while_last_check_healthy(monkeypatch):
    gate, clock, _ = _gate([])
    assert health_loop.heartbeat_due_ok(gate, now=0) is False  # never checked
    gate.record_health(True)
    assert health_loop.heartbeat_due_ok(gate, now=gate.last_health_at + 10) is True
    assert health_loop.heartbeat_due_ok(gate, now=gate.last_health_at + 10_000) is False  # stale
    gate.record_health(False)
    assert health_loop.heartbeat_due_ok(gate, now=gate.last_health_at + 1) is False


def test_heartbeat_pings_env_url_and_is_off_when_unset(monkeypatch):
    monkeypatch.delenv(health_loop.HEARTBEAT_ENV, raising=False)
    assert health_loop.ping_heartbeat() is False

    class Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    seen = []
    monkeypatch.setattr(health_loop.urllib.request, "urlopen", lambda url, timeout: seen.append(url) or Resp())
    monkeypatch.setenv(health_loop.HEARTBEAT_ENV, "https://uptime.betterstack.com/api/v1/heartbeat/abc")
    assert health_loop.ping_heartbeat() is True
    assert seen == ["https://uptime.betterstack.com/api/v1/heartbeat/abc"]
