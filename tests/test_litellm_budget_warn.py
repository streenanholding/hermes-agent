"""scripts/litellm_budget_warn.py: warn once at 80% of max_budget per period."""

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "litellm_budget_warn",
    Path(__file__).resolve().parent.parent / "scripts" / "litellm_budget_warn.py",
)
warn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(warn)


def key(spend, cap=100.0, reset="2026-10-27T00:00:00Z"):
    return {"spend": spend, "max_budget": cap, "budget_reset_at": reset}


def test_no_warning_below_threshold():
    state = {}
    assert warn.evaluate("sol", key(79.9), state, 80) is None and state == {}


def test_warns_at_threshold_once_per_period():
    state = {}
    msg = warn.evaluate("sol", key(80), state, 80)
    assert msg and "Sol" in msg and "80%" in msg and "$80.00 of $100.00" in msg
    assert warn.evaluate("sol", key(95), state, 80) is None  # same period: quiet


def test_rewarns_after_reset_or_dip():
    state = {}
    warn.evaluate("sol", key(85), state, 80)
    assert warn.evaluate("sol", key(85, reset="2026-11-03T00:00:00Z"), state, 80)  # new period
    warn.evaluate("sol", key(10), state, 80)  # dropped under: record cleared
    assert warn.evaluate("sol", key(90, reset="2026-11-03T00:00:00Z"), state, 80)


def test_keys_without_max_budget_are_ignored():
    assert warn.evaluate("carol", {"spend": 500, "max_budget": None}, {}, 80) is None


def test_run_checks_each_agent_and_posts_only_crossers(tmp_path, monkeypatch):
    monkeypatch.setenv("LITELLM_BASE_URL", "http://litellm")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-admin")
    spend = {"sol": 50, "carly": 85, "seraphine": 100, "carol": 10}
    posted = []
    out = warn.run(
        aliases={a: a for a in warn.AGENTS},
        threshold_pct=80,
        state_file=tmp_path / "state.json",
        dry_run=False,
        fetch=lambda base, admin, alias: key(spend[alias]),
        post=lambda text: posted.append(text) or True,
    )
    assert len(out) == 2 and len(posted) == 2
    assert {"Carly", "Seraphine"} == {m.split("'")[0].split()[-1] for m in out}
    # second run is silent (state persisted)
    again = warn.run(
        aliases={a: a for a in warn.AGENTS},
        threshold_pct=80,
        state_file=tmp_path / "state.json",
        dry_run=False,
        fetch=lambda base, admin, alias: key(spend[alias]),
        post=lambda text: posted.append(text) or True,
    )
    assert again == [] and len(posted) == 2


def test_failed_post_is_retried_next_run(tmp_path, monkeypatch):
    monkeypatch.setenv("LITELLM_BASE_URL", "http://litellm")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-admin")
    kwargs = dict(
        aliases={"sol": "sol"},
        threshold_pct=80,
        state_file=tmp_path / "s.json",
        dry_run=False,
        fetch=lambda *a: key(90),
    )
    assert warn.run(post=lambda t: False, **kwargs)
    assert warn.run(post=lambda t: True, **kwargs)  # warned again: first post never landed


def test_requires_env(monkeypatch, tmp_path):
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
    monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
    with pytest.raises(SystemExit):
        warn.run(aliases={"sol": "sol"}, threshold_pct=80, state_file=tmp_path / "s", dry_run=True)
