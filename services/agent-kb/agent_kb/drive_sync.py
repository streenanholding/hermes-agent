"""Google Drive -> library sync (FIN-1413).

Rick manages content by putting Google Docs (or .md / .txt files) in the
"Agent Knowledge Library" folder. Each subfolder name is the audience:
`all`, `sol`, `carly`, `seraphine`, `carol`. A file that is removed, trashed or
moved out is retired on the next sync. Read-only Drive scope.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
import urllib.parse
import urllib.request
from datetime import date
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from . import chunking, phi
from .store import Doc

log = logging.getLogger("agent_kb.drive")

_API = "https://www.googleapis.com/drive/v3"
_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
_TEXT_TYPES = {"text/plain", "text/markdown", "text/x-markdown"}
_GDOC = "application/vnd.google-apps.document"
_FOLDER = "application/vnd.google-apps.folder"
PREFIX = "drive-"


def _b64(b: bytes) -> bytes:
    return base64.urlsafe_b64encode(b).rstrip(b"=")


class DriveClient:
    def __init__(self, sa_json: str) -> None:
        self._sa = json.loads(sa_json)
        self._tok: Tuple[str, float] = ("", 0.0)

    @property
    def client_email(self) -> str:
        return self._sa.get("client_email", "")

    def _token(self) -> str:
        if self._tok[1] > time.time():
            return self._tok[0]
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        now = int(time.time())
        head = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        claims = _b64(json.dumps({"iss": self._sa["client_email"], "scope": _SCOPE,
                                  "aud": "https://oauth2.googleapis.com/token", "iat": now, "exp": now + 3600}).encode())
        key = serialization.load_pem_private_key(self._sa["private_key"].encode(), password=None)
        sig = _b64(key.sign(head + b"." + claims, padding.PKCS1v15(), hashes.SHA256()))
        body = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                       "assertion": (head + b"." + claims + b"." + sig).decode()}).encode()
        with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=body), timeout=30) as r:
            tok = json.loads(r.read())
        self._tok = (tok["access_token"], time.time() + int(tok.get("expires_in", 3600)) - 60)
        return self._tok[0]

    def _get(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + self._token()})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()

    def children(self, folder_id: str) -> List[dict]:
        out, page = [], None
        while True:
            q = {"q": f"'{folder_id}' in parents and trashed=false", "supportsAllDrives": "true",
                 "includeItemsFromAllDrives": "true", "pageSize": 200,
                 "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,webViewLink)"}
            if page:
                q["pageToken"] = page
            data = json.loads(self._get(f"{_API}/files?" + urllib.parse.urlencode(q)))
            out += data.get("files", [])
            page = data.get("nextPageToken")
            if not page:
                return out

    def text(self, f: dict) -> str:
        if f["mimeType"] == _GDOC:
            url = f"{_API}/files/{f['id']}/export?mimeType=text%2Fplain"
        else:
            url = f"{_API}/files/{f['id']}?alt=media&supportsAllDrives=true"
        return self._get(url).decode("utf-8", errors="replace").lstrip("﻿")


def walk(client, folder_id: str, audiences: Iterable[str], depth: int = 3) -> List[Tuple[dict, str]]:
    """Return (file, audience) for every supported file under the library folder."""
    found: List[Tuple[dict, str]] = []
    allowed = set(audiences)

    def rec(fid: str, aud: str, d: int) -> None:
        for f in client.children(fid):
            if f["mimeType"] == _FOLDER:
                if d > 0:
                    rec(f["id"], aud, d - 1)
            elif f["mimeType"] == _GDOC or f["mimeType"] in _TEXT_TYPES or f["name"].lower().endswith((".md", ".txt")):
                found.append((f, aud))

    for top in client.children(folder_id):
        if top["mimeType"] == _FOLDER and top["name"].strip().lower() in allowed:
            rec(top["id"], top["name"].strip().lower(), depth)
    return found


class DriveSync:
    def __init__(self, store, embedder, client, folder_id: str, audiences: Iterable[str],
                 interval_s: int = 300, on_done: Optional[Callable[[dict], None]] = None) -> None:
        self.store, self.embedder, self.client = store, embedder, client
        self.folder_id, self.audiences, self.interval_s = folder_id, tuple(audiences), interval_s
        self.on_done = on_done
        self._seen_mtime: Dict[str, str] = {}
        self.last: dict = {}

    def run_once(self) -> dict:
        files = walk(self.client, self.folder_id, self.audiences)
        by_id: Dict[str, Tuple[dict, List[str]]] = {}
        for f, aud in files:  # same file shortcut-linked under two audiences -> union
            by_id.setdefault(PREFIX + f["id"].lower(), (f, []))[1].append(aud)

        active_prev = {d.doc_id for d in self.store.list_docs() if d.status == "active" and d.doc_id.startswith(PREFIX)}
        loaded, unchanged, rejected = 0, 0, []
        for doc_id, (f, auds) in by_id.items():
            stamp = f.get("modifiedTime", "") + "|" + ",".join(sorted(auds))
            if self._seen_mtime.get(doc_id) == stamp and doc_id in active_prev:
                unchanged += 1
                continue
            text = self.client.text(f)
            hits = phi.findings(f["name"] + "\n" + text)
            texts = chunking.chunk(text)
            if hits or not texts:
                rejected.append({"title": f["name"], "reason": hits or ["empty"]})
                if doc_id in active_prev:
                    self.store.retire(doc_id)
                continue
            eff = (f.get("modifiedTime") or "")[:10]
            self.store.upsert(Doc(doc_id, f["name"], f.get("webViewLink"), "drive",
                                  date.fromisoformat(eff) if eff else None, sorted(set(auds))),
                              texts, self.embedder.embed_docs(texts))
            self._seen_mtime[doc_id] = stamp
            loaded += 1

        retired = 0
        for doc_id in active_prev - set(by_id):
            self.store.retire(doc_id)
            self._seen_mtime.pop(doc_id, None)
            retired += 1

        self.last = {"at": int(time.time()), "files": len(by_id), "loaded": loaded, "unchanged": unchanged,
                     "retired": retired, "rejected": rejected}
        log.info("drive sync: %s", json.dumps(self.last))
        if self.on_done:
            self.on_done(self.last)
        return self.last

    def start(self) -> threading.Thread:
        def loop():
            while True:
                try:
                    self.run_once()
                except Exception:
                    log.exception("drive sync failed")
                time.sleep(self.interval_s)

        t = threading.Thread(target=loop, name="drive-sync", daemon=True)
        t.start()
        return t


def from_env(store, embedder, audiences, on_done=None) -> Optional[DriveSync]:
    sa, folder = os.environ.get("KB_GOOGLE_SA_JSON"), os.environ.get("KB_DRIVE_FOLDER_ID")
    if not (sa and folder):
        log.info("drive sync off (KB_GOOGLE_SA_JSON / KB_DRIVE_FOLDER_ID not set)")
        return None
    client = DriveClient(sa)
    log.info("drive sync on: folder=%s as %s", folder, client.client_email)
    return DriveSync(store, embedder, client, folder, audiences,
                     int(os.environ.get("KB_SYNC_SECONDS", "300")), on_done)
