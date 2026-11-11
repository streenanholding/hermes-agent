"""Drive sync (FIN-1413): folders decide audience; removed files retire; PHI files are skipped."""

from __future__ import annotations

import pytest

from agent_kb.app import _env_agent_tokens
from agent_kb.drive_sync import PREFIX, DriveSync
from agent_kb.store import MemoryStore
from test_agent_kb import HashEmbedder

FOLDER = "application/vnd.google-apps.folder"
GDOC = "application/vnd.google-apps.document"


class FakeDrive:
    def __init__(self):
        self.tree = {
            "root": [{"id": "fAll", "name": "all", "mimeType": FOLDER},
                     {"id": "fSol", "name": "sol", "mimeType": FOLDER},
                     {"id": "fJunk", "name": "random", "mimeType": FOLDER}],
            "fAll": [{"id": "Pricing1", "name": "Pricing v3", "mimeType": GDOC, "modifiedTime": "2026-11-10T00:00:00Z",
                      "webViewLink": "https://docs.google.com/x"}],
            "fSol": [{"id": "Cap1", "name": "Cap table", "mimeType": "text/markdown", "modifiedTime": "2026-11-10T00:00:00Z"}],
            "fJunk": [{"id": "J1", "name": "ignored", "mimeType": GDOC, "modifiedTime": "2026-11-10T00:00:00Z"}],
        }
        self.body = {"Pricing1": "Annual price per location is 398 per month.",
                     "Cap1": "Cap table and SAFE allocations.", "J1": "should never load"}
        self.reads = 0

    def children(self, fid):
        return self.tree.get(fid, [])

    def text(self, f):
        self.reads += 1
        return self.body[f["id"]]


@pytest.fixture()
def sync():
    store, drive = MemoryStore(), FakeDrive()
    return DriveSync(store, HashEmbedder(), drive, "root", ("all", "sol", "carly", "seraphine", "carol")), store, drive


def test_loads_by_folder_audience(sync):
    s, store, _ = sync
    r = s.run_once()
    assert r["loaded"] == 2 and r["files"] == 2
    assert store.docs[PREFIX + "pricing1"].audience == ["all"]
    assert store.docs[PREFIX + "cap1"].audience == ["sol"]
    assert store.docs[PREFIX + "pricing1"].source_url == "https://docs.google.com/x"


def test_unchanged_files_are_not_reread(sync):
    s, _, drive = sync
    s.run_once()
    reads = drive.reads
    assert s.run_once()["unchanged"] == 2 and drive.reads == reads


def test_edit_reloads_new_version(sync):
    s, store, drive = sync
    s.run_once()
    drive.tree["fAll"][0]["modifiedTime"] = "2026-11-11T00:00:00Z"
    drive.body["Pricing1"] = "Annual price per location is 398 per month. Updated."
    assert s.run_once()["loaded"] == 1
    assert store.docs[PREFIX + "pricing1"].version == 2


def test_removed_file_is_retired(sync):
    s, store, drive = sync
    s.run_once()
    drive.tree["fSol"] = []
    assert s.run_once()["retired"] == 1
    assert store.docs[PREFIX + "cap1"].status == "retired"


def test_phi_file_is_skipped_and_retired(sync):
    s, store, drive = sync
    s.run_once()
    drive.tree["fAll"][0]["modifiedTime"] = "2026-11-12T00:00:00Z"
    drive.body["Pricing1"] = "Patient name: Jane Doe"
    r = s.run_once()
    assert r["rejected"] and store.docs[PREFIX + "pricing1"].status == "retired"


def test_env_tokens(monkeypatch):
    monkeypatch.delenv("KB_AGENT_TOKENS", raising=False)
    monkeypatch.setenv("KB_TOKEN_SOL", "s" * 40)
    monkeypatch.setenv("KB_TOKEN_CARLY", "c" * 40)
    assert _env_agent_tokens() == {"s" * 40: "sol", "c" * 40: "carly"}
    monkeypatch.setenv("KB_TOKEN_SERAPHINE", "short")
    with pytest.raises(ValueError):
        _env_agent_tokens()
