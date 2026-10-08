# deploy/carly

Persona and config for hermes-carly (Carly Finkle, Chief of Staff to the Executive Chairman).

## What Hermes loads (from /opt/data, the Railway volume, HERMES_HOME)

- `SOUL.md` is her identity (loaded from HERMES_HOME).
- `AGENTS.md` is her charter. Gateway sessions use `$HOME` (/opt/data) as the working directory, and Hermes reads AGENTS.md from the working directory, so it must sit in /opt/data.
- `config.yaml` holds settings only (model, toolsets). It holds no prompt.
- `slack-manifest.json` is not loaded by Hermes. It is pasted into the Slack app (see below).

## Refreshing the persona on every deploy

Railway does NOT mount volumes during the pre-deploy step, so a preDeployCommand cannot write to /opt/data. The copy has to run in the Start Command, which runs with the volume mounted. It copies only AGENTS.md and SOUL.md every deploy and seeds config.yaml only when it is missing. It never touches memory, sessions or other state.

Start Command:

```
sh -c 'test -f /opt/data/config.yaml || { cp /opt/hermes/deploy/carly/config.yaml /opt/data/config.yaml && chown hermes:hermes /opt/data/config.yaml; }; cp /opt/hermes/deploy/carly/AGENTS.md /opt/hermes/deploy/carly/SOUL.md /opt/data/ && chown hermes:hermes /opt/data/AGENTS.md /opt/data/SOUL.md; exec /opt/hermes/docker/entrypoint-dispatch.sh gateway'
```

Leave the Pre-Deploy Command empty.

To change config.yaml on a running volume, copy it once by hand (or add it to the cp list for one deploy, then remove it). Copying it every deploy would overwrite runtime edits.

## Environment variables (names only; set in Railway, never stored in this repo)

- HERMES_HOME
- PORT
- HERMES_DASHBOARD
- OPENAI_BASE_URL
- OPENAI_API_KEY (a LiteLLM virtual key for Carly, $40 per 30 days)
- SLACK_BOT_TOKEN
- SLACK_APP_TOKEN
- SLACK_ALLOWED_USERS
- SLACK_HOME_CHANNEL

Google access (Gmail, Calendar, Drive) is not wired yet. AGENTS.md section 11 tells her to say so plainly until it is.

## Slack app

Create the app from `slack-manifest.json` (Socket Mode on). It was generated with `hermes slack manifest`, so its scopes match Hermes' default Slack app.
