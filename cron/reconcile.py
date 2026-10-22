"""Make an agent's live cron store match ``deploy/<agent>/cron/jobs.yaml``.

The yaml file is the complete list of jobs the agent may have. ``reconcile``:

* creates a listed job that does not exist (matched by name),
* resets an existing listed job to the listed schedule/prompt/script/model
  (and re-enables it, clearing any breaker pause), and
* deletes every job whose name is not listed.

Run on every boot by ``docker/stage2-hook.sh`` and from ``python -m cron.reconcile
<jobs.yaml>``. ``--dry-run`` prints the plan without touching the store.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

REQUIRED = ("name", "schedule")
# Fields compared/applied on an existing job. Values are (yaml key, job key).
_RESET_FIELDS = (("prompt", "prompt"), ("model", "model"), ("script", "script"))


def load_spec(path: "str | Path") -> List[Dict[str, Any]]:
    import yaml

    data = yaml.safe_load(Path(path).read_text()) or {}
    jobs = data.get("jobs") or []
    seen = set()
    for j in jobs:
        missing = [k for k in REQUIRED if not j.get(k)]
        if missing:
            raise ValueError(f"cron spec entry {j!r} missing {missing}")
        if not (j.get("prompt") or j.get("script")):
            raise ValueError(f"cron job {j['name']!r} needs a prompt or a script")
        if j["name"] in seen:
            raise ValueError(f"duplicate cron job name {j['name']!r}")
        seen.add(j["name"])
    return jobs


def _schedule_text(job: Dict[str, Any]) -> str:
    sched = job.get("schedule")
    if isinstance(sched, dict):
        return str(sched.get("expr") or sched.get("display") or "")
    return str(sched or "")


def plan(spec: List[Dict[str, Any]], live: List[Dict[str, Any]]) -> Dict[str, list]:
    want = {j["name"]: j for j in spec}
    by_name = {j.get("name"): j for j in live}
    return {
        "create": [n for n in want if n not in by_name],
        "reset": [n for n in want if n in by_name],
        "delete": [j for j in live if j.get("name") not in want],
    }


def reconcile(spec: List[Dict[str, Any]], *, dry_run: bool = False) -> Dict[str, list]:
    from cron import jobs as cj

    live = cj.list_jobs(include_disabled=True)
    todo = plan(spec, live)
    if dry_run:
        return {"created": todo["create"], "reset": todo["reset"], "deleted": [j.get("name") for j in todo["delete"]]}

    deleted: List[str] = []
    for j in todo["delete"]:
        try:
            if cj.remove_job(j["id"]):
                deleted.append(j.get("name") or j["id"])
        except Exception:
            logger.exception("could not delete unlisted cron job %s", j.get("name"))

    want = {j["name"]: j for j in spec}
    by_name = {j.get("name"): j for j in live}
    created: List[str] = []
    reset: List[str] = []
    for name in todo["create"]:
        j = want[name]
        try:
            cj.create_job(
                prompt=j.get("prompt"), schedule=j["schedule"], name=name, model=j.get("model"),
                no_agent=bool(j.get("no_agent")), script=j.get("script"), deliver=j.get("deliver", "local"),
            )
            created.append(name)
        except Exception:
            logger.exception("could not create cron job %s", name)
    for name in todo["reset"]:
        j, cur = want[name], by_name[name]
        updates: Dict[str, Any] = {k: j.get(y) for y, k in _RESET_FIELDS if cur.get(k) != j.get(y)}
        if _schedule_text(cur) != j["schedule"]:
            updates["schedule"] = j["schedule"]
        if bool(cur.get("no_agent")) != bool(j.get("no_agent")):
            updates["no_agent"] = bool(j.get("no_agent"))
        if not cur.get("enabled", True) or cur.get("state") == "paused":
            updates.update({"enabled": True, "state": "scheduled", "paused_at": None, "paused_reason": None,
                            "paused_by": None, "failure_streak": 0})
        if not updates:
            continue
        try:
            if cj.update_job(cur["id"], updates):
                reset.append(name)
        except Exception:
            logger.exception("could not reset cron job %s", name)
    return {"created": created, "reset": reset, "deleted": deleted}


def main(argv: List[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print("usage: python -m cron.reconcile <jobs.yaml> [--dry-run]", file=sys.stderr)
        return 2
    result = reconcile(load_spec(args[0]), dry_run="--dry-run" in argv)
    print(f"cron reconcile: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
