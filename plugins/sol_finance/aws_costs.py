"""AWS Cost Explorer + Budgets, read only. Cached; at most one live pull per ISO week."""

from __future__ import annotations

import datetime as dt
import os
from typing import Any, Dict

from . import common

_CACHE = "aws_cost_cache.json"


def _client(service: str):
    import boto3  # in the image via the bedrock extra

    return boto3.client(service, region_name="us-east-1",
                        aws_access_key_id=os.environ.get("AWS_SOL_BILLING_ACCESS_KEY_ID"),
                        aws_secret_access_key=os.environ.get("AWS_SOL_BILLING_SECRET_ACCESS_KEY"))


def _week() -> str:
    y, w, _ = dt.date.today().isocalendar()
    return f"{y}-W{w:02d}"


def cost_by_month(start: str = None) -> Dict[str, Any]:
    cache = common.load_state(_CACHE, {})
    if cache.get("week") == _week() and not start:
        return {**cache["data"], "cached": True}
    if cache.get("week") == _week():
        return {**cache["data"], "cached": True, "note": "one live pull per week; returning cache"}
    today = dt.date.today()
    start = start or f"{today.year}-01-01"
    end = (today + dt.timedelta(days=1)).isoformat()
    ce = _client("ce")
    r = ce.get_cost_and_usage(TimePeriod={"Start": start, "End": end}, Granularity="MONTHLY",
                              Metrics=["UnblendedCost"], GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}])
    months = []
    for row in r.get("ResultsByTime", []):
        groups = {g["Keys"][0]: round(float(g["Metrics"]["UnblendedCost"]["Amount"]), 2) for g in row.get("Groups", [])}
        months.append({"month": row["TimePeriod"]["Start"][:7], "total": round(sum(groups.values()), 2),
                       "top_services": dict(sorted(groups.items(), key=lambda kv: -kv[1])[:5])})
    data = {"from": start, "through": end, "months": months,
            "total": round(sum(m["total"] for m in months), 2)}
    common.save_state(_CACHE, {"week": _week(), "data": data})
    return {**data, "cached": False}


def budgets() -> Dict[str, Any]:
    acct = _client("sts").get_caller_identity()["Account"]
    r = _client("budgets").describe_budgets(AccountId=acct)
    return {"budgets": [{"name": b["BudgetName"], "limit": b["BudgetLimit"],
                         "actual": b.get("CalculatedSpend", {}).get("ActualSpend")} for b in r.get("Budgets", [])]}
