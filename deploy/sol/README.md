# deploy/sol

Sol Rosenthal (FinVerified finance agent), FIN-954. Seeded onto the Railway volume at `/opt/data`
when `HERMES_AGENT_DEPLOY=sol` (see `docker/stage2-hook.sh`). `config.yaml`, `SOUL.md`, `AGENTS.md`,
`skills/` and `templates/` are overwritten from the image on every boot so PR review is the only way
to change them; Sol's memory and state live elsewhere on the volume.

Railway variables (names only): MERCURY_READ_TOKEN, STRIPE_SOL_READ_KEY, XERO_CLIENT_ID,
XERO_CLIENT_SECRET, AWS_SOL_BILLING_ACCESS_KEY_ID, AWS_SOL_BILLING_SECRET_ACCESS_KEY,
GOOGLE_SOL_SA_JSON, SLACK_BOT_TOKEN, SLACK_APP_TOKEN, OPENAI_API_KEY, OPENAI_BASE_URL, HERMES_HOME,
PORT, HERMES_AGENT_DEPLOY=sol, SOL_RICK_SLACK_ID, SOL_NANCY_SLACK_ID, SOL_PUBLIC_URL,
GMAIL_SOL_REFRESH_TOKEN (after one-time consent), GOOGLE_OAUTH_CLIENT_ID/SECRET (Gmail consent).
