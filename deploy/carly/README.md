# deploy/carly

Persona and config for hermes-carly (Carly Finkle, Chief of Staff to the Executive Chairman).

Hermes reads config.yaml, SOUL.md and AGENTS.md from /opt/data (the Railway volume, HERMES_HOME).

Environment variable names the service expects (set in Railway; values are never stored in this repo):

- HERMES_HOME
- PORT
- HERMES_DASHBOARD
- OPENAI_BASE_URL
- OPENAI_API_KEY
- SLACK_BOT_TOKEN
- SLACK_APP_TOKEN
- SLACK_ALLOWED_USERS
- SLACK_HOME_CHANNEL

The first boot copies this folder into the volume only when config.yaml is missing. Later changes to these files do not reach a running volume on their own (see the PR description for the refresh options).
