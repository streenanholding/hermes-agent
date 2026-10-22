"""80% budget warning: once per budget period, silent otherwise."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "common" / "scripts" / "budget_warn.py"
spec = importlib.util.spec_from_file_location("budget_warn", SCRIPT)
bw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bw)


def _info(spend, cap=100, reset="2026-11-01"):
    return {"spend": spend, "max_budget": cap, "budget_reset_at": reset}


def test_below_80_is_silent():
    assert bw.decide(_info(79.9), None, 80)[0] is None


def test_at_80_warns_with_numbers():
    msg, period = bw.decide(_info(80), None, 80)
    assert "80%" in msg and "$80.00 of $100.00" in msg and period == "2026-11-01"


def test_same_period_never_warns_twice_new_period_does():
    assert bw.decide(_info(95), "2026-11-01", 80)[0] is None
    assert bw.decide(_info(95, reset="2026-12-01"), "2026-11-01", 80)[0] is not None


def test_no_cap_means_nothing_to_warn_about():
    assert bw.decide({"spend": 500, "max_budget": None}, None, 80)[0] is None


def test_main_records_period_only_after_rick_was_told(monkeypatch, tmp_path):
    from gateway import ops_alerts

    ops_alerts.reset_for_tests()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("BUDGET_WARN_SIMULATE", "90,100")
    monkeypatch.setattr(ops_alerts, "_send_dm", lambda t: False)
    assert bw.main() == 0 and not bw.state_path().exists()  # DM failed: retry next run
    ops_alerts.reset_for_tests()
    sent = []
    monkeypatch.setattr(ops_alerts, "_send_dm", lambda t: sent.append(t) or True)
    assert bw.main() == 0 and len(sent) == 1 and bw.state_path().exists()
    ops_alerts.reset_for_tests()
    assert bw.main() == 0 and len(sent) == 1  # same period: silent
