"""Daily scripted budget check (no model call). Output is logged; DMs go to Rick only when a threshold is crossed."""
import json
import os
import sys

sys.path.insert(0, os.environ.get("HERMES_INSTALL_DIR", "/opt/hermes"))

from plugins.sol_finance import budget  # noqa: E402

res = budget.check_and_notify()
print(json.dumps({"spent_usd": res["status"]["spent_usd"], "alerts_sent": res["alerts_sent"],
                  "alerts_failed": res["alerts_failed"]}))
