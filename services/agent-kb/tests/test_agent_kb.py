"""agent-kb tests (FIN-1413). Run: cd services/agent-kb && python -m pytest -q"""

from __future__ import annotations

import hashlib
import math
import re

import pytest
from fastapi.testclient import TestClient

from agent_kb import chunking, phi
from agent_kb.app import _parse_agent_tokens, create_app
from agent_kb.store import MemoryStore

SOL, CARLY, SERA, ADMIN = "s" * 40, "c" * 40, "r" * 40, "a" * 40


class HashEmbedder:
    """Deterministic bag-of-words embedder: shared words => similar vectors."""

    def _v(self, text):
        v = [0.0] * 64
        for w in re.findall(r"[a-z0-9]+", text.lower()):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 64] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def embed_docs(self, texts):
        return [self._v(t) for t in texts]

    def embed_query(self, text):
        return self._v(text)


@pytest.fixture()
def env():
    store = MemoryStore()
    app = create_app(store=store, embedder=HashEmbedder(),
                     agent_tokens={SOL: "sol", CARLY: "carly", SERA: "seraphine"}, admin_token=ADMIN)
    with TestClient(app) as c:
        yield c, store


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def load(c, **kw):
    body = {"doc_id": "pricing-v3", "title": "Pricing v3", "owner": "rick", "audience": ["all"],
            "text": "Annual price per location is 398 dollars per month under an annual commitment."}
    body.update(kw)
    return c.post("/admin/docs", json=body, headers=H(ADMIN))


def search(c, tok, q):
    return c.post("/v1/search", json={"query": q}, headers=H(tok))


def test_pricing_answer_with_citation(env):
    c, _ = env
    assert load(c).status_code == 200
    r = search(c, CARLY, "what is our annual price per location")
    assert r.status_code == 200
    top = r.json()["results"][0]
    assert "398" in top["text"] and top["title"] == "Pricing v3" and top["doc_id"] == "pricing-v3"


def test_audience_isolation(env):
    c, _ = env
    load(c, doc_id="cap-table", title="Cap table summary", audience=["sol"],
         text="Cap table summary and SAFE investor allocations for the strategic round.")
    assert search(c, SOL, "cap table SAFE investor allocations").json()["results"]
    assert search(c, CARLY, "cap table SAFE investor allocations").json()["results"] == []
    assert search(c, SERA, "cap table SAFE investor allocations").json()["results"] == []


def test_agent_cannot_choose_audience(env):
    c, _ = env
    load(c, doc_id="cap-table", title="Cap table", audience=["sol"], text="Cap table investor allocations.")
    r = c.post("/v1/search", json={"query": "cap table investor allocations", "audience": "sol"}, headers=H(CARLY))
    assert r.json()["results"] == [] and r.json()["agent"] == "carly"


def test_retire_removes_from_results(env):
    c, _ = env
    load(c, doc_id="defense-plan", title="Legal defense plan pricing",
         text="Legal defense plan embedded in every pricing tier.")
    assert search(c, SOL, "legal defense plan pricing tier").json()["results"]
    assert c.post("/admin/docs/defense-plan/retire", headers=H(ADMIN)).json()["status"] == "retired"
    assert search(c, SOL, "legal defense plan pricing tier").json()["results"] == []


def test_reload_bumps_version_and_reactivates(env):
    c, _ = env
    assert load(c).json()["version"] == 1
    c.post("/admin/docs/pricing-v3/retire", headers=H(ADMIN))
    r = load(c)
    assert r.json()["version"] == 2 and r.json()["status"] == "active"


@pytest.mark.parametrize("bad", [
    "Patient name: Jane Doe, visit notes",
    "SSN 123-45-6789 on file",
    "DOB: 01/02/1980",
    "MRN: 4455667",
    "card 4111 1111 1111 1111 exp 12/29",
])
def test_phi_rejected(env, bad):
    c, store = env
    r = load(c, doc_id="bad-doc", title="Notes", text="Weekly notes. " + bad)
    assert r.status_code == 422
    assert "bad-doc" not in store.docs


def test_clean_business_text_passes_phi_check():
    assert phi.findings("Pricing v3: 468 month-to-month, 398 annual, 4298.40 prepaid. NMLS 1234567.") == []


def test_agents_have_no_write_route(env):
    c, _ = env
    assert load(c).status_code == 200
    assert c.post("/admin/docs", json={}, headers=H(SOL)).status_code == 401
    assert c.post("/admin/docs/pricing-v3/retire", headers=H(CARLY)).status_code == 401
    assert c.get("/admin/docs", headers=H(SERA)).status_code == 401


def test_auth_required(env):
    c, _ = env
    assert c.post("/v1/search", json={"query": "hi there"}).status_code == 401
    assert search(c, "x" * 40, "hi there").status_code == 401
    assert c.get("/health").json() == {"ok": True}


def test_unknown_audience_rejected(env):
    c, _ = env
    assert load(c, audience=["vivian"]).status_code == 422


def test_search_is_logged_without_query_text(env):
    c, store = env
    load(c)
    search(c, SOL, "annual price per location")
    agent, results, _latency, _at = store.searches[-1]
    assert agent == "sol" and results >= 1
    assert c.get("/admin/stats", headers=H(ADMIN)).json()["searches_7d"] == 1


def test_token_config_validation():
    assert _parse_agent_tokens('{"sol": "%s"}' % ("z" * 40)) == {"z" * 40: "sol"}
    with pytest.raises(ValueError):
        _parse_agent_tokens('{"sol": "short"}')
    with pytest.raises(ValueError):
        _parse_agent_tokens('{"jordan": "%s"}' % ("z" * 40))


def test_chunking_respects_size():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 120 for i in range(20))
    parts = chunking.chunk(text)
    assert len(parts) > 1 and all(len(p) <= chunking.MAX_CHARS + chunking.OVERLAP_CHARS + 10 for p in parts)
    assert chunking.chunk("") == []
