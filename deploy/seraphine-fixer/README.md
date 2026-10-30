# seraphine-fixer (Seraphine Auto-Fixer v4)

Seraphine's hands. A small Bun service on Railway (project `agent-platform`,
service `seraphine-fixer`) that receives every Better Stack incident, patrols
every platform every 5 minutes, repairs what it is allowed to repair, and
silences the call when it has verified the fix. Ticket: FIN-1231.

Until v4 the source lived only as base64 inside the Railway start command
(`./run.sh <base64>`). `legacy/fixer-v3.ts` is that exact v3 source, decoded
read-only on Oct 30 2026, kept for reference. It is not deployed from here.

## The 4-minute window (do not remove)

Every Better Stack incident goes to the fixer first (outgoing webhook
"Seraphine Auto-Fixer", Incident started/reopened → `POST /betterstack`). The
"FinVerified Sev-1" escalation policy waits **4 minutes** before calling
people. In that window she confirms, repairs and verifies:

1. Confirm it is really down: 2 failed checks, 15 s apart.
2. Certificate or DNS problem? Never restart. Put back the DNS record or explain.
3. Restart. Check every 15 s until it is healthy **twice in a row**.
4. Still down and the newest release is under 2 h old? Roll back (never the API).
5. Healthy twice in a row → **acknowledge, then resolve** the incident with a note
   ("Seraphine restarted X at 12:03; healthy since 12:04"). Inside 4 minutes
   nobody is called. Not healthy, or flapping → she leaves it unacknowledged
   and the call goes out at minute 4.

Time-to-detect and time-to-fix are logged for every incident
(`{"event":"incident",...}` lines). The window is intentional (decided Oct 16,
FIN-937). Never set it to 0.

## What else she does

| | Plain code ($0 AI) | AI |
|---|---|---|
| Outage repair, ack/resolve, rate limits | ✅ | – |
| One Slack thread per problem (same problem within 6 h bumps the count) | ✅ | – |
| Error alerts: pull 30 min of error lines, group by pattern, match the rulebook | ✅ | – |
| Pattern not in the rulebook | cache first | `seraphine-fast`, once per pattern |
| Blind-spot watch, every patrol | ✅ | – |
| Daily IT report (8 AM ET) with an AI spend line | ✅ | – |
| Weekly uptime report (Mondays 9 AM ET) | ✅ | `seraphine-strong` for the risk summary, max once a week |
| Monthly staging drill (off until configured) | ✅ | – |

**Rulebook v1** (`src/rulebook.ts`): S3 AccessDenied → IAM permission (Rick);
SSM ParameterNotFound → missing parameter, named (Rick); DB connection
refused/timeouts → restart API, then check Postgres; vendor 401 → key rotated
or expired (Rick, FIN-1152); cert/DNS → her existing DNS/certificate path;
PLAN_NOT_STARTED / 4xx floods → product issue, Linear Bug for Ashish. Plus two
noise rows seen in production logs (the `LOG_CANARY` line and ticket test
lines). Each AI diagnosis Rick confirms becomes a new row here, by PR.

**AI metering** (`src/ai.ts`): only through LiteLLM on her own capped virtual
key (`SERAPHINE_LITELLM_KEY`). At 80% of the cap she says so in Slack once a
day; at 100% AI stops and every code path keeps running. Diagnoses are cached
by pattern (text with ids stripped), so a pattern is paid for once. The model
sees only the scrubbed pattern and a count (`src/scrub.ts` removes ids,
emails, phones, keys, names, dates of birth, member ids, addresses).

**Blind-spot watch** (`src/blindspots.ts`): each production log source got
logs recently; each scheduled job's heartbeat line is fresh; the latest
`e2e-prod-smoke` run is green; certificates are renewing; Postgres backups ran
in the last 24 h. Findings get one #alerts thread. With `BLINDSPOT_PAGE=on`
she also opens a Better Stack incident (calls people) once per 24 h per finding.

## Safe list and never-list

She may: restart; roll back a release under 2 h old (not the API); put back a
website DNS address record to the copy she saw working; acknowledge/resolve an
incident after 2 healthy checks; post to #alerts; open/update a Linear Bug;
stop a **staging** service during the drill.

She never touches: code, databases, environment variables or secrets, IAM,
users, money; never deletes anything; never touches MX/TXT records. This is
enforced in `src/policy.ts`: any other Railway mutation or Cloudflare write
throws before a request is sent (see `tests/policy.test.ts`).

## Variables

Set in Railway on the `seraphine-fixer` service only. Never in code.

Already set (unchanged): `FIXER_KEY`, `RAILWAY_TOKEN_APP`, `RAILWAY_TOKEN_WEBSITE`,
`RAILWAY_TOKEN_SANDBOX`, `RAILWAY_TOKEN_WALKTHROUGH`, `RAILWAY_TOKEN_ACADEMY`,
`RAILWAY_TOKEN_AGENTS`, `CLOUDFLARE_API_TOKEN`, `SLACK_WEBHOOK_URL`,
`BETTERSTACK_API_TOKEN` (now also used to resolve and comment),
`BETTERSTACK_HEARTBEAT_URL`. Optional as before: `CLOUDFLARE_ZONE_ID`.

New in v4:

| Variable | Needed for | Without it |
|---|---|---|
| `BETTERSTACK_SQL_URL`, `BETTERSTACK_SQL_USER`, `BETTERSTACK_SQL_PASSWORD` | Read-only log queries (Better Stack Telemetry → Integrations → SQL API → ClickHouse HTTP client) | No log diagnosis, no log-source/job/backup checks |
| `GITHUB_ACTIONS_TOKEN` | Read-only: latest `e2e-prod-smoke` run (fine-grained token, `RHE-LLC/FinVerified.ai`, Actions: read) | Smoke test not watched |
| `SERAPHINE_LITELLM_KEY` | AI for unknown patterns. Her existing capped LiteLLM virtual key (same value as `OPENAI_API_KEY` on `hermes-seraphine`) | Code-only mode (still works) |
| `SLACK_BOT_TOKEN`, `SLACK_ALERTS_CHANNEL` | Editing the original message and threading (bot needs `chat:write` and to be in #alerts; channel id like `C0…`) | Repeats within 6 h are counted silently; follow-ups post as new messages |
| `LINEAR_API_KEY` | One Linear Bug per product cause | Diagnosis says so; no Bug |
| `STATE_FILE` | Keep the AI cache, threads and incident log across restarts (needs a volume, e.g. `/data/seraphine-state.json`) | Starts fresh after a restart |

Tuning (all optional): `BETTERSTACK_PROD_SOURCES` (default
`t534306_finverified_app_oct27`), `BLINDSPOT_LOG_SILENCE_MIN` (default 30),
`BLINDSPOT_PAGE` (`on` to page), `JOB_HEARTBEATS` (JSON list of
`{name, match, maxHours}`), `BACKUP_CHECK` (JSON `{match, maxHours}`),
`SMOKE_REPO`, `SMOKE_WORKFLOW`, `UPTIME_TARGET` (default 99.99),
`AI_WEEKLY_CAP_USD` (fallback only; LiteLLM's cap is the real one),
`LITELLM_BASE_URL`, `LINEAR_TEAM_ID`, `BETTERSTACK_REQUESTER_EMAIL`.
Drill: `DRILL_TARGET` (JSON, staging only; production ids are refused), the
token variable it names, and `DRILL_SCHEDULE=on` for the first Tuesday each month.

## Run, test, deploy

```sh
cd deploy/seraphine-fixer
bun test                  # every decision path, no network
bun src/main.ts           # local run (needs the variables above)
```

Dry runs on the live service (nothing changes): `GET /test?key=<FIXER_KEY>&target=`
`api.finverified.ai` · `dns:<host>` · `cloudflare` · `scenario` · `agents` ·
`blindspots` · `diagnose:<error text>`. Posting: `report`, `weekly`,
`drill:fixable`, `drill:unfixable`.

Deploy only by PR; Rick merges. The service builds from this folder
(`Dockerfile`, `railway.json`) when Railway is pointed at the repo with root
directory `/deploy/seraphine-fixer`.
