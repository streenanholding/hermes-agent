"""Stripe: READ ONLY via restricted key. GET only."""

from __future__ import annotations

import os
from typing import Any, Dict
from urllib.parse import urlencode

from . import common

READABLE = {"balance", "charges", "payouts", "subscriptions", "balance_transactions"}


def get(resource: str, **params: Any) -> Any:
    if resource not in READABLE:
        raise PermissionError(f"stripe resource not allowed: {resource}")
    q = urlencode({k: v for k, v in params.items() if v is not None})
    return common.http_json("GET", f"https://api.stripe.com/v1/{resource}" + (f"?{q}" if q else ""),
                            headers={"Authorization": "Bearer " + os.environ.get("STRIPE_SOL_READ_KEY", "")})


def summary() -> Dict[str, Any]:
    subs = get("subscriptions", status="active", limit=100)
    mrr = 0
    for s in subs.get("data", []):
        for it in (s.get("items", {}) or {}).get("data", []):
            p = it.get("price") or {}
            amt = (p.get("unit_amount") or 0) * (it.get("quantity") or 1)
            interval = (p.get("recurring") or {}).get("interval")
            mrr += amt / 12 if interval == "year" else amt
    return {"balance": get("balance"), "active_subscriptions": len(subs.get("data", [])),
            "mrr_cents_estimate": round(mrr), "payouts": get("payouts", limit=10).get("data", []),
            "has_more_subscriptions": subs.get("has_more", False)}
