"""Storage. PgStore is production (pgvector, own `agent_kb` schema); MemoryStore backs the tests."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Sequence

from .embedder import DIM


@dataclass
class Doc:
    doc_id: str
    title: str
    source_url: Optional[str]
    owner: str
    effective_date: Optional[date]
    audience: List[str]
    status: str = "active"
    version: int = 1
    chunk_count: int = 0
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Hit:
    doc_id: str
    title: str
    source_url: Optional[str]
    effective_date: Optional[date]
    version: int
    text: str
    score: float


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryStore:
    """In-process store with the same semantics as PgStore. Used by tests only."""

    def __init__(self) -> None:
        self.docs: Dict[str, Doc] = {}
        self.chunks: Dict[str, List[tuple]] = {}
        self.searches: List[tuple] = []
        self._lock = threading.Lock()

    def init(self) -> None:
        pass

    def upsert(self, doc: Doc, texts: Sequence[str], vectors: Sequence[Sequence[float]]) -> Doc:
        with self._lock:
            prev = self.docs.get(doc.doc_id)
            doc.version = (prev.version + 1) if prev else 1
            doc.status, doc.chunk_count, doc.updated_at = "active", len(texts), _now()
            self.docs[doc.doc_id] = doc
            self.chunks[doc.doc_id] = list(zip(texts, vectors))
            return doc

    def retire(self, doc_id: str) -> Optional[Doc]:
        with self._lock:
            d = self.docs.get(doc_id)
            if d:
                d.status, d.updated_at = "retired", _now()
            return d

    def list_docs(self) -> List[Doc]:
        return sorted(self.docs.values(), key=lambda d: d.doc_id)

    def search(self, qvec: Sequence[float], audiences: Sequence[str], k: int) -> List[Hit]:
        def cos(a, b):
            na = math.sqrt(sum(x * x for x in a)) or 1.0
            nb = math.sqrt(sum(x * x for x in b)) or 1.0
            return sum(x * y for x, y in zip(a, b)) / (na * nb)

        hits = []
        for d in self.docs.values():
            if d.status != "active" or not set(d.audience) & set(audiences):
                continue
            for text, vec in self.chunks.get(d.doc_id, []):
                hits.append(Hit(d.doc_id, d.title, d.source_url, d.effective_date, d.version, text, cos(qvec, vec)))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]

    def log_search(self, agent: str, results: int, latency_ms: int) -> None:
        self.searches.append((agent, results, latency_ms, _now()))

    def stats(self) -> dict:
        active = [d for d in self.docs.values() if d.status == "active"]
        return {"active_docs": len(active), "retired_docs": len(self.docs) - len(active),
                "chunks": sum(d.chunk_count for d in active), "searches_7d": len(self.searches)}


_SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS agent_kb;
CREATE TABLE IF NOT EXISTS agent_kb.docs (
  doc_id         text PRIMARY KEY,
  title          text NOT NULL,
  source_url     text,
  owner          text NOT NULL,
  effective_date date,
  audience       text[] NOT NULL,
  status         text NOT NULL DEFAULT 'active' CHECK (status IN ('active','retired')),
  version        int  NOT NULL DEFAULT 1,
  chunk_count    int  NOT NULL DEFAULT 0,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS agent_kb.chunks (
  id        bigserial PRIMARY KEY,
  doc_id    text NOT NULL REFERENCES agent_kb.docs(doc_id) ON DELETE CASCADE,
  ord       int  NOT NULL,
  text      text NOT NULL,
  embedding vector({DIM}) NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw ON agent_kb.chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_doc ON agent_kb.chunks(doc_id);
CREATE TABLE IF NOT EXISTS agent_kb.searches (
  id         bigserial PRIMARY KEY,
  agent      text NOT NULL,
  results    int  NOT NULL,
  latency_ms int  NOT NULL,
  at         timestamptz NOT NULL DEFAULT now()
);
"""


def _vec(v: Sequence[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


class PgStore:
    def __init__(self, dsn: str) -> None:
        from psycopg_pool import ConnectionPool

        self.pool = ConnectionPool(dsn, min_size=1, max_size=4, open=True,
                                   kwargs={"options": "-c search_path=agent_kb,public"})

    def init(self) -> None:
        with self.pool.connection() as c:
            c.execute(_SCHEMA)

    def upsert(self, doc: Doc, texts: Sequence[str], vectors: Sequence[Sequence[float]]) -> Doc:
        with self.pool.connection() as c, c.transaction():
            row = c.execute(
                """INSERT INTO agent_kb.docs (doc_id,title,source_url,owner,effective_date,audience,status,chunk_count)
                   VALUES (%s,%s,%s,%s,%s,%s,'active',%s)
                   ON CONFLICT (doc_id) DO UPDATE SET title=EXCLUDED.title, source_url=EXCLUDED.source_url,
                     owner=EXCLUDED.owner, effective_date=EXCLUDED.effective_date, audience=EXCLUDED.audience,
                     status='active', chunk_count=EXCLUDED.chunk_count, version=agent_kb.docs.version+1, updated_at=now()
                   RETURNING version, updated_at""",
                (doc.doc_id, doc.title, doc.source_url, doc.owner, doc.effective_date, list(doc.audience), len(texts)),
            ).fetchone()
            c.execute("DELETE FROM agent_kb.chunks WHERE doc_id=%s", (doc.doc_id,))
            with c.cursor() as cur:
                cur.executemany(
                    "INSERT INTO agent_kb.chunks (doc_id,ord,text,embedding) VALUES (%s,%s,%s,%s::vector)",
                    [(doc.doc_id, i, t, _vec(v)) for i, (t, v) in enumerate(zip(texts, vectors))],
                )
        doc.version, doc.updated_at, doc.chunk_count, doc.status = row[0], row[1], len(texts), "active"
        return doc

    def retire(self, doc_id: str) -> Optional[Doc]:
        with self.pool.connection() as c:
            c.execute("UPDATE agent_kb.docs SET status='retired', updated_at=now() WHERE doc_id=%s", (doc_id,))
        return next((d for d in self.list_docs() if d.doc_id == doc_id), None)

    def list_docs(self) -> List[Doc]:
        with self.pool.connection() as c:
            rows = c.execute(
                "SELECT doc_id,title,source_url,owner,effective_date,audience,status,version,chunk_count,updated_at "
                "FROM agent_kb.docs ORDER BY doc_id").fetchall()
        return [Doc(r[0], r[1], r[2], r[3], r[4], list(r[5]), r[6], r[7], r[8], r[9]) for r in rows]

    def search(self, qvec: Sequence[float], audiences: Sequence[str], k: int) -> List[Hit]:
        with self.pool.connection() as c:
            rows = c.execute(
                """SELECT d.doc_id, d.title, d.source_url, d.effective_date, d.version, ch.text,
                          1 - (ch.embedding <=> %s::vector) AS score
                   FROM agent_kb.chunks ch JOIN agent_kb.docs d USING (doc_id)
                   WHERE d.status='active' AND d.audience && %s::text[]
                   ORDER BY ch.embedding <=> %s::vector LIMIT %s""",
                (_vec(qvec), list(audiences), _vec(qvec), k),
            ).fetchall()
        return [Hit(*r) for r in rows]

    def log_search(self, agent: str, results: int, latency_ms: int) -> None:
        with self.pool.connection() as c:
            c.execute("INSERT INTO agent_kb.searches (agent,results,latency_ms) VALUES (%s,%s,%s)",
                      (agent, results, latency_ms))

    def stats(self) -> dict:
        with self.pool.connection() as c:
            r = c.execute(
                """SELECT (SELECT count(*) FROM agent_kb.docs WHERE status='active'),
                          (SELECT count(*) FROM agent_kb.docs WHERE status='retired'),
                          (SELECT coalesce(sum(chunk_count),0) FROM agent_kb.docs WHERE status='active'),
                          (SELECT count(*) FROM agent_kb.searches WHERE at > now() - interval '7 days')""").fetchone()
            by_agent = dict(c.execute(
                "SELECT agent, count(*) FROM agent_kb.searches WHERE at > now() - interval '7 days' GROUP BY agent").fetchall())
        return {"active_docs": r[0], "retired_docs": r[1], "chunks": int(r[2]), "searches_7d": r[3],
                "searches_7d_by_agent": by_agent}
