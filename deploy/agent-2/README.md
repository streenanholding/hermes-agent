# hermes-agent-2 (Agent 2, name TBD): connections & enrollment

FIN-878 (parent FIN-646). Dark build: no patient data, no bank data, no sending.
Pattern: `deploy/seraphine/`.

| File | What |
|---|---|
| `CAPABILITIES.md` | The capability contract. Installed as `/opt/data/AGENTS.md` so Hermes loads it. |
| `SOUL.md` | Identity. Installed as `/opt/data/SOUL.md`. |
| `config.yaml` | Model routing, prompt caching, toolset allowlist, delegation, cron policy |
| `cron/jobs.yaml` | The five scheduled jobs, all `no_agent` scripts |
| `scripts/` | Budget guard, draft check, stale check, roll-up, weekly spend |
| `quality/prohibited-claims.txt` | Phrases that fail the draft check |
| `templates/trackers/` | Vendor and per-practice payer-enrollment trackers |
| `templates/drafts/` | Approved draft templates (email, follow-up, enrollment request, application answers, call brief) |
| `templates/skills/` | Payer-enrollment skill template for the learning loop |
| `install.sh` | Copies the above onto the volume and registers the cron jobs |
| `tests/` | `python -m pytest deploy/agent-2/tests -q`, synthetic data only |

## Setup (Rick; nothing here is deployed by the PR)

Secrets are set directly in Railway, LiteLLM and Slack. Never paste them in chat or commit them.

1. **LiteLLM** (admin UI)
   - Model aliases: `agent2-claude-haiku` → Claude Haiku 4.5 (`claude-haiku-4-5-20251001`),
     `agent2-claude-sonnet` → Claude Sonnet 5.5 (`claude-sonnet-5-5`),
     `agent2-claude-opus` → Claude Opus 5.5 (`claude-opus-5-5`).
     Keep `claude` in the alias names: Hermes only enables prompt caching on a LiteLLM route when the model name is Claude.
   - New virtual key `hermes-agent-2`: allowed models = those three aliases only;
     `max_budget` = the weekly cap in USD; `budget_duration` = `7d`. Optional: a
     per-model budget on `agent2-claude-opus`.
2. **Slack**: a new app (not Seraphine's).
   - Create it from `hermes slack manifest --agent-view --write` (run in the
     service shell after first boot), or manually per
     `website/docs/user-guide/messaging/slack.md`.
   - Socket Mode on. App-level token with `connections:write` (`xapp-`).
   - Bot scopes: `chat:write`, `app_mentions:read`, `channels:history`,
     `channels:read`, `groups:history`, `im:history`, `im:read`, `im:write`,
     `mpim:history`, `mpim:read`, `users:read`, `files:read`; optional `assistant:write`.
     `files:write` is not needed.
   - Events: `message.im`, `message.channels`, `message.groups`, `app_mention`
     (plus `message.mpim` if you'll use group DMs).
   - App Home → Messages Tab on. Install to workspace (`xoxb-` bot token).
   - Create a private channel for the agent, invite the bot, note its channel ID.
3. **Better Stack**: a new Logs source `hermes-agent-2`. Note its source token and ingesting host.
4. **Railway**, project `agent-platform`
   - New service `hermes-agent-2` from `streenanholding/hermes-agent`, branch
     `main`, Dockerfile build. Persistent volume mounted at `/opt/data`.
   - Variables:

     | Variable | Value |
     |---|---|
     | `HERMES_HOME` | `/opt/data` |
     | `OPENAI_API_KEY` | the `hermes-agent-2` LiteLLM virtual key (secret) |
     | `AGENT2_LITELLM_KEY` | `${{OPENAI_API_KEY}}` (Railway reference, not a second copy) |
     | `AGENT2_LITELLM_BASE_URL` | `https://litellm-gateway-production-774e.up.railway.app` |
     | `SLACK_BOT_TOKEN` | `xoxb-` bot token (secret) |
     | `SLACK_APP_TOKEN` | `xapp-` app-level token (secret) |
     | `SLACK_ALLOWED_USERS` | Rick's Slack member ID (comma-separated if Nancy too) |
     | `SLACK_HOME_CHANNEL` | the agent channel's ID |
     | `SLACK_HOME_CHANNEL_NAME` | the agent channel's name |
     | `AGENT2_RICK_SLACK_ID` | Rick's Slack member ID (for escalation mentions) |
     | `HERMES_WRITE_SAFE_ROOT` | `/opt/data/trackers:/opt/data/drafts/pending:/opt/data/logs/opus` |
     | `AGENT2_BETTER_STACK_SOURCE_TOKEN` | Better Stack source token (secret) |
     | `AGENT2_BETTER_STACK_INGESTING_HOST` | Better Stack ingesting host |

   - Must **not** exist on this service: any GitHub, Railway, Google, SMTP,
     Telnyx or database credential, `DATABASE_URL`, or a direct provider key
     (`ANTHROPIC_API_KEY` etc.).
5. In the service shell: `bash /opt/hermes/deploy/agent-2/install.sh`, then restart the service.
6. Confirm `timezone` in `config.yaml` (set to `America/New_York`) before the first deploy.

## Verifying "done" (FIN-878)

Against synthetic vendors and practices only:
- Ask a status question in the channel. It answers from the tracker.
- Ask for a follow-up draft. It lands in `drafts/pending/` and posts within 5 min as `READY FOR RICK TO SEND`. Nothing is sent.
- `hermes cron run <agent2-stale-check id>`. Flags at 5 business days, escalates at 10.
- Budget drill: set a tiny `max_budget` on the key, or run `AGENT2_BUDGET_SIMULATE_SPEND_PCT=100 python /opt/data/scripts/budget_guard.py`, and confirm the stop message and that LiteLLM rejects calls.
