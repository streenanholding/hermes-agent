"""Local AI-spend estimate, used only when LiteLLM won't let Sol's key read its own spend.

Fed by the post_api_request hook with token counts and priced at published rates.
It undercounts anything spent before the ledger existed or outside this volume, so
every message built from it says "estimated".
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from . import common

# USD per million tokens (input, output). Cache reads cost 10% of input, cache writes 125%.
PRICES = {"haiku": (1.0, 5.0), "sonnet": (3.0, 15.0)}
_FILE = "usage_ledger.json"


def _price(model: str) -> Optional[Tuple[float, float]]:
    m = (model or "").lower()
    for key, p in PRICES.items():
        if key in m:
            return p
    return None


def cost_usd(model: str, usage: Dict[str, Any]) -> float:
    p = _price(model) or PRICES["sonnet"]  # unknown model: assume the dearer one
    i, o = p
    return (usage.get("input_tokens", 0) * i + usage.get("output_tokens", 0) * o
            + usage.get("cache_read_tokens", 0) * i * 0.10
            + usage.get("cache_write_tokens", 0) * i * 1.25) / 1_000_000


def record(model: str, usage: Optional[Dict[str, Any]]) -> None:
    if not usage:
        return
    led = common.load_state(_FILE, {})
    month = led.setdefault(time.strftime("%Y-%m"), {})
    row = month.setdefault(model or "unknown", {"usd": 0.0, "calls": 0})
    row["usd"] = round(row["usd"] + cost_usd(model, usage), 6)
    row["calls"] += 1
    common.save_state(_FILE, led)


def estimate_month() -> Tuple[float, list]:
    month = common.load_state(_FILE, {}).get(time.strftime("%Y-%m"), {})
    rows = [{"model": k, "usd": round(v["usd"], 4)} for k, v in sorted(month.items(), key=lambda kv: -kv[1]["usd"])]
    return round(sum(r["usd"] for r in rows), 4), rows
