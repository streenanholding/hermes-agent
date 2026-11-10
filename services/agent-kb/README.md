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

## Content never goes in this repo

This repository is public. Documents are loaded into the database through the admin
API only. Keep the source files in a private place.

## Access

| Who | Token | Can do |
|---|---|---|
| Each agent | its own token in `KB_AGENT_TOKENS` | `POST /v1/search` only. Sees documents tagged with its own name or `all`. |
| Rick | `KB_ADMIN_TOKEN` | Load, retire, list, stats. |

An agent's audience comes from its token on the server, so an agent cannot ask for
another agent's documents.

## Railway variables (names only)

- `DATABASE_URL`: reference to `pgvector-db` (Railway reference variables).
- `KB_AGENT_TOKENS`: JSON, for example `{"sol": "<token>", "carly": "<token>", "seraphine": "<token>"}`. Each token is at least 32 characters.
- `KB_ADMIN_TOKEN`: at least 32 characters.
- `KB_MIN_SCORE` (optional, default 0.30).

On each agent service:
- `AGENT_KB_URL=http://agent-kb.railway.internal:8080`
- `AGENT_KB_TOKEN=<that agent's token>`

The `kb_search` tool stays hidden until both are set.

## Loading documents

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
