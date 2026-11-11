# agent-kb

FinVerified's agent knowledge library (FIN-1413). Sol, Carly and Seraphine search
approved company documents through one read-only tool, `kb_search`, and cite the
source in their answers.

## What it is

- A small FastAPI service on Railway (project `agent-platform`), next to the Hermes agents.
- Storage: the existing `pgvector-db` service, in its own `agent_kb` schema. It never
  connects to the FinVerified app database.
- Embeddings: `BAAI/bge-small-en-v1.5`, run locally on CPU and baked into the image.
  Zero per-call API cost.
- No PHI: every document is checked on load, and anything that looks like patient data
  or a card/ID number is rejected.

## Adding and removing documents (Google Drive)

Content lives in the **Agent Knowledge Library** folder in the *FinVerified Finance*
shared drive. Each subfolder name is who can read it: `all`, `sol`, `carly`,
`seraphine`, `carol`. Google Docs, `.md` and `.txt` files are picked up.

- Add or edit a doc: it is loaded within 5 minutes.
- Delete it or move it out: it is retired within 5 minutes.
- A doc that looks like it contains patient data is skipped (see the logs).

Content never goes in this repo, which is public.

## Access

| Who | Token | Can do |
|---|---|---|
| Each agent | its own `KB_TOKEN_<AGENT>` | `POST /v1/search` only. Sees documents tagged with its own name or `all`. |
| Rick | the Drive folder (and optional `KB_ADMIN_TOKEN`) | Add, edit, remove documents. |

An agent's audience comes from its token on the server, so an agent cannot ask for
another agent's documents.

## Railway variables (names only)

- `DATABASE_URL`: reference to `pgvector-db` (Railway reference variables).
- `KB_TOKEN_SOL`, `KB_TOKEN_CARLY`, `KB_TOKEN_SERAPHINE` (optional `KB_TOKEN_CAROL`): one random value per agent, at least 32 characters. Set by Rick; never pasted anywhere else.
- `KB_GOOGLE_SA_JSON`: reference to Sol's service account (read-only scope is used).
- `KB_DRIVE_FOLDER_ID`: the Agent Knowledge Library folder.
- `KB_ADMIN_TOKEN` (optional): enables the admin API for scripted loads.
- `KB_MIN_SCORE` (optional, default 0.30).

On each agent service:
- `AGENT_KB_URL=http://agent-kb.railway.internal:8080`
- `AGENT_KB_TOKEN=${{agent-kb.KB_TOKEN_<AGENT>}}` (a Railway reference, so the value is typed once).

The `kb_search` tool stays hidden until both are set.

## Scripted loading (optional, needs KB_ADMIN_TOKEN)

```
export KB_URL=<agent-kb URL> KB_ADMIN_TOKEN=<admin token>
python kb_admin.py load ./my-private-docs/
python kb_admin.py retire defense-plan
python kb_admin.py list
python kb_admin.py stats
```

Front matter format is in `kb_admin.py`.

## Tests

```
cd services/agent-kb && python -m pytest -q
```
