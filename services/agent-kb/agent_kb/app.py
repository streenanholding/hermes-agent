"""agent-kb: FinVerified's agent knowledge library (FIN-1413).

Read path (agents):  POST /v1/search   Bearer <agent token>  -> passages + citations
Write path (Rick):   POST /admin/docs, POST /admin/docs/{id}/retire, GET /admin/docs, GET /admin/stats
                     Bearer <admin token>

Who an agent is comes from its token, never from the request, so one agent can
never ask for another agent's documents. Agents have no write route at all.
Nothing here connects to the FinVerified app database.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import date
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

from . import chunking, phi
from .embedder import Embedder, LocalEmbedder
from .store import Doc, MemoryStore, PgStore

log = logging.getLogger("agent_kb")

AGENTS = ("sol", "carly", "seraphine", "carol")
AUDIENCES = AGENTS + ("all",)
MAX_DOC_CHARS = 400_000
MIN_SCORE = float(os.environ.get("KB_MIN_SCORE", "0.30"))


def _env_agent_tokens() -> Dict[str, str]:
    """Per-agent tokens from KB_TOKEN_SOL, KB_TOKEN_CARLY, ... (preferred), plus legacy KB_AGENT_TOKENS JSON."""
    out = _parse_agent_tokens(os.environ.get("KB_AGENT_TOKENS", ""))
    for agent in AGENTS:
        tok = os.environ.get(f"KB_TOKEN_{agent.upper()}", "").strip()
        if tok:
            if len(tok) < 32:
                raise ValueError(f"KB_TOKEN_{agent.upper()} must be at least 32 characters")
            out[tok] = agent
    return out


def _parse_agent_tokens(raw: str) -> Dict[str, str]:
    """KB_AGENT_TOKENS = JSON {"sol": "<token>", "carly": "<token>", ...}. Returns token -> agent."""
    if not raw:
        return {}
    data = json.loads(raw)
    out = {}
    for agent, token in data.items():
        if agent not in AGENTS:
            raise ValueError(f"unknown agent in KB_AGENT_TOKENS: {agent}")
        if not isinstance(token, str) or len(token) < 32:
            raise ValueError(f"token for {agent} must be at least 32 characters")
        out[token] = agent
    return out


class DocIn(BaseModel):
    doc_id: str = Field(min_length=2, max_length=120)
    title: str = Field(min_length=2, max_length=300)
    text: str = Field(min_length=1)
    owner: str = Field(default="rick", max_length=80)
    source_url: Optional[str] = Field(default=None, max_length=2000)
    effective_date: Optional[date] = None
    audience: List[str] = Field(min_length=1)

    @field_validator("doc_id")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", v):
            raise ValueError("doc_id must be a lowercase slug (a-z, 0-9, . _ -)")
        return v

    @field_validator("audience")
    @classmethod
    def _aud(cls, v: List[str]) -> List[str]:
        bad = [a for a in v if a not in AUDIENCES]
        if bad:
            raise ValueError(f"unknown audience {bad}; allowed: {list(AUDIENCES)}")
        return sorted(set(v))


class SearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    k: int = Field(default=5, ge=1, le=10)


def create_app(store=None, embedder: Optional[Embedder] = None, agent_tokens: Optional[Dict[str, str]] = None,
               admin_token: Optional[str] = None, start_sync: bool = False) -> FastAPI:
    if store is None:
        dsn = os.environ.get("DATABASE_URL")
        store = PgStore(dsn) if dsn else MemoryStore()
    embedder = embedder or LocalEmbedder()
    tokens = agent_tokens if agent_tokens is not None else _env_agent_tokens()
    admin = admin_token if admin_token is not None else os.environ.get("KB_ADMIN_TOKEN", "")
    if admin and len(admin) < 32:
        raise ValueError("KB_ADMIN_TOKEN must be at least 32 characters")

    canary_q = os.environ.get("KB_CANARY_QUERY", "what is our annual price per location")

    def _canary(_summary: dict) -> None:
        """Log which document answers a known question, so a deploy can be checked from logs alone."""
        try:
            hits = store.search(embedder.embed_query(canary_q), list(AUDIENCES), 1)
            log.info("canary: %r -> %s", canary_q,
                     f"{hits[0].title} (score {hits[0].score:.2f})" if hits else "no result")
        except Exception:
            log.exception("canary failed")

    @asynccontextmanager
    async def lifespan(_app):
        store.init()
        log.info("agent-kb ready: agents with access = %s", sorted(set(tokens.values())))
        if start_sync:
            from . import drive_sync

            sync = drive_sync.from_env(store, embedder, AUDIENCES, on_done=_canary)
            if sync:
                sync.start()
        yield

    app = FastAPI(title="agent-kb", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    def _bearer(authorization: str) -> str:
        if not authorization.lower().startswith("bearer "):
            raise HTTPException(401, "missing bearer token")
        return authorization[7:].strip()

    def agent_auth(authorization: str = Header(default="")) -> str:
        tok = _bearer(authorization)
        for known, agent in tokens.items():
            if hmac.compare_digest(known, tok):
                return agent
        raise HTTPException(401, "invalid token")

    def admin_auth(authorization: str = Header(default="")) -> None:
        if not admin or not hmac.compare_digest(admin, _bearer(authorization)):
            raise HTTPException(401, "invalid token")

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/v1/search")
    def search(body: SearchIn, agent: str = Depends(agent_auth)):
        t0 = time.monotonic()
        hits = store.search(embedder.embed_query(body.query), [agent, "all"], body.k)
        hits = [h for h in hits if h.score >= MIN_SCORE]
        store.log_search(agent, len(hits), int((time.monotonic() - t0) * 1000))
        return {
            "agent": agent,
            "results": [
                {"doc_id": h.doc_id, "title": h.title, "source_url": h.source_url,
                 "effective_date": h.effective_date.isoformat() if h.effective_date else None,
                 "version": h.version, "score": round(float(h.score), 3), "text": h.text}
                for h in hits
            ],
            "note": "Cite the title (and link if present) when you state a fact from these results."
                    if hits else "No approved source found. Say so instead of guessing.",
        }

    @app.post("/admin/docs", dependencies=[Depends(admin_auth)])
    def upsert(body: DocIn):
        if len(body.text) > MAX_DOC_CHARS:
            raise HTTPException(413, f"document too large (max {MAX_DOC_CHARS} characters)")
        found = phi.findings(body.title + "\n" + body.text)
        if found:
            raise HTTPException(422, {"error": "possible PHI or sensitive identifiers; document rejected",
                                      "patterns": found})
        texts = chunking.chunk(body.text)
        if not texts:
            raise HTTPException(422, "document has no text")
        vectors = embedder.embed_docs(texts)
        doc = store.upsert(Doc(body.doc_id, body.title, body.source_url, body.owner, body.effective_date,
                               body.audience), texts, vectors)
        return {"doc_id": doc.doc_id, "version": doc.version, "chunks": doc.chunk_count, "status": doc.status}

    @app.post("/admin/docs/{doc_id}/retire", dependencies=[Depends(admin_auth)])
    def retire(doc_id: str):
        d = store.retire(doc_id)
        if not d:
            raise HTTPException(404, "no such document")
        return {"doc_id": d.doc_id, "status": d.status}

    @app.get("/admin/docs", dependencies=[Depends(admin_auth)])
    def list_docs():
        return {"docs": [
            {"doc_id": d.doc_id, "title": d.title, "owner": d.owner, "audience": d.audience, "status": d.status,
             "version": d.version, "chunks": d.chunk_count,
             "effective_date": d.effective_date.isoformat() if d.effective_date else None,
             "updated_at": d.updated_at.isoformat() if d.updated_at else None}
            for d in store.list_docs()]}

    @app.get("/admin/stats", dependencies=[Depends(admin_auth)])
    def stats():
        return store.stats()

    return app


def main() -> None:  # pragma: no cover - container entrypoint
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(start_sync=True), host="::", port=int(os.environ.get("PORT", "8080")), access_log=False)


if __name__ == "__main__":  # pragma: no cover
    main()
