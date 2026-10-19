#!/usr/bin/env bash
# Install Agent 2's files onto its Railway volume and register its cron jobs.
#
# Run by Rick from a Railway shell on the hermes-agent-2 service, from the repo
# checkout inside the image:   bash /opt/hermes/deploy/agent-2/install.sh
# Idempotent: re-run after any merged change to deploy/agent-2/.
#
# Copies files only. It never writes a credential, never prints the
# environment, and never deploys anything.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOME_DIR="${HERMES_HOME:-/opt/data}"

if [[ "$HOME_DIR" != "/opt/data" ]]; then
  echo "HERMES_HOME is '$HOME_DIR', expected /opt/data. Refusing to install." >&2
  exit 1
fi

mkdir -p "$HOME_DIR"/{scripts,templates,quality,state,skills} \
         "$HOME_DIR"/trackers/{vendors,practices} \
         "$HOME_DIR"/drafts/{pending,posted,failed} \
         "$HOME_DIR"/logs/opus

# Identity, contract, config. The contract is installed as AGENTS.md in the
# working directory (terminal.cwd) so Hermes loads it into the system prompt.
install -m 0644 "$SRC/SOUL.md"          "$HOME_DIR/SOUL.md"
install -m 0644 "$SRC/CAPABILITIES.md"  "$HOME_DIR/AGENTS.md"
install -m 0644 "$SRC/config.yaml"      "$HOME_DIR/config.yaml"

# Templates and quality rules (read-only for the agent: outside HERMES_WRITE_SAFE_ROOT).
rm -rf "$HOME_DIR/templates"
cp -R "$SRC/templates" "$HOME_DIR/templates"
install -m 0644 "$SRC/quality/prohibited-claims.txt" "$HOME_DIR/quality/prohibited-claims.txt"

# Cron scripts.
for f in "$SRC"/scripts/*.py; do
  install -m 0755 "$f" "$HOME_DIR/scripts/$(basename "$f")"
done

touch "$HOME_DIR/logs/opus/reasons.md"

# Register cron jobs from cron/jobs.yaml (skip any that already exist by name).
# Use the interpreter Hermes itself runs on (it has PyYAML). Unquoted on
# purpose: the shebang may be "/usr/bin/env python3".
PY="$(sed -n '1s/^#!//p' "$(command -v hermes)" 2>/dev/null || true)"
PY="${PY:-python3}"
existing="$(hermes cron list --all 2>/dev/null || true)"
$PY - "$SRC/cron/jobs.yaml" <<'PY' | while IFS=$'\t' read -r name schedule script deliver; do
import sys, yaml
for j in yaml.safe_load(open(sys.argv[1]))["jobs"]:
    print("\t".join([j["name"], j["schedule"], j["script"], j["deliver"]]))
PY
  if grep -q -- "$name" <<<"$existing"; then
    echo "cron: $name already registered, leaving it"
  else
    hermes cron create "$schedule" --name "$name" --script "$script" --no-agent --deliver "$deliver"
    echo "cron: registered $name ($schedule)"
  fi
done

echo "Agent 2 files installed in $HOME_DIR. Restart the service to load config.yaml."
