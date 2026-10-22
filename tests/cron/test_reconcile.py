"""cron.reconcile: the live store is made to match the agent's jobs.yaml."""

from pathlib import Path

import pytest
import yaml

from cron import jobs, reconcile

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
AGENTS = ("sol", "carly", "seraphine", "carol")


def _spec(*names, schedule="0 9 * * *"):
    return [{"name": n, "schedule": schedule, "prompt": f"do {n}"} for n in names]


def _names():
    return sorted(j["name"] for j in jobs.list_jobs(include_disabled=True))


def test_creates_listed_jobs():
    result = reconcile.reconcile(_spec("a", "b"))
    assert sorted(result["created"]) == ["a", "b"] and _names() == ["a", "b"]


def test_deletes_every_unlisted_job_including_paused_ones():
    jobs.create_job(prompt="x", schedule="every 1h", name="stray", deliver="local")
    paused = jobs.create_job(prompt="x", schedule="every 1h", name="paused-stray", deliver="local")
    jobs.pause_job(paused["id"]) if hasattr(jobs, "pause_job") else jobs.update_job(paused["id"], {"enabled": False, "state": "paused"})
    result = reconcile.reconcile(_spec("keep"))
    assert sorted(result["deleted"]) == ["paused-stray", "stray"] and _names() == ["keep"]


def test_resets_wrong_schedule_and_prompt():
    jobs.create_job(prompt="old", schedule="every 5m", name="a", deliver="local")
    result = reconcile.reconcile(_spec("a", schedule="0 7 * * 5"))
    live = [j for j in jobs.list_jobs(include_disabled=True) if j["name"] == "a"][0]
    assert result["reset"] == ["a"] and live["prompt"] == "do a"
    assert live["schedule"]["expr"] == "0 7 * * 5"


def test_reenables_a_breaker_paused_job():
    j = jobs.create_job(prompt="do a", schedule="0 9 * * *", name="a", deliver="local")
    jobs.update_job(j["id"], {"enabled": False, "state": "paused", "paused_by": "circuit_breaker", "failure_streak": 3})
    reconcile.reconcile(_spec("a"))
    live = jobs.get_job(j["id"])
    assert live["enabled"] is True and live["state"] != "paused" and live["failure_streak"] == 0


def test_idempotent():
    reconcile.reconcile(_spec("a", "b"))
    again = reconcile.reconcile(_spec("a", "b"))
    assert again == {"created": [], "reset": [], "deleted": []}


def test_dry_run_changes_nothing():
    jobs.create_job(prompt="x", schedule="every 1h", name="stray", deliver="local")
    plan = reconcile.reconcile(_spec("new"), dry_run=True)
    assert plan["created"] == ["new"] and plan["deleted"] == ["stray"] and _names() == ["stray"]


@pytest.mark.parametrize("bad", [[{"schedule": "0 9 * * *", "prompt": "x"}], [{"name": "a", "schedule": "0 9 * * *"}]])
def test_rejects_malformed_entries(tmp_path, bad):
    f = tmp_path / "jobs.yaml"
    f.write_text(yaml.safe_dump({"jobs": bad}))
    with pytest.raises(ValueError):
        reconcile.load_spec(f)


@pytest.mark.parametrize("agent", AGENTS)
def test_shipped_specs_load_and_every_schedule_parses(agent):
    spec = reconcile.load_spec(DEPLOY / agent / "cron" / "jobs.yaml")
    assert spec
    for j in spec:
        assert j["name"].startswith(agent + "-")
        jobs.parse_schedule(j["schedule"])


def test_sol_friday_report_is_7am_friday():
    spec = {j["name"]: j for j in reconcile.load_spec(DEPLOY / "sol" / "cron" / "jobs.yaml")}
    assert spec["sol-weekly-cfo-report-fri"]["schedule"] == "0 7 * * 5"
    assert "rick@finverified.ai" in spec["sol-weekly-cfo-report-fri"]["prompt"]
    assert "ncoy@finverified.ai" in spec["sol-weekly-cfo-report-fri"]["prompt"]


def test_sol_plugin_seeds_from_the_same_spec():
    from plugins.sol_finance import schedules

    assert [j["name"] for j in schedules.JOBS] == [j["name"] for j in reconcile.load_spec(DEPLOY / "sol" / "cron" / "jobs.yaml")]
