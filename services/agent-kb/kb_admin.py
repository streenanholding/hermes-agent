#!/usr/bin/env python3
"""Load, retire and list agent-kb documents.

Content NEVER lives in this repo (it is public). Keep the markdown files in a
private place (Google Drive, your laptop) and point this script at them.

Each file starts with a front-matter block:

    ---
    doc_id: pricing-v3
    title: Pricing v3 (canonical)
    audience: all            # comma list: sol, carly, seraphine, carol, all
    effective_date: 2026-09-28
    source_url: https://drive.google.com/...   (optional)
    owner: rick
    ---
    body text...

Usage (env: KB_URL, KB_ADMIN_TOKEN):
    python kb_admin.py load  <file-or-folder> [...]
    python kb_admin.py retire <doc_id>
    python kb_admin.py list
    python kb_admin.py stats
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.error
import urllib.request


def _req(method: str, path: str, body=None):
    url = os.environ["KB_URL"].rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + os.environ["KB_ADMIN_TOKEN"], "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "detail": e.read().decode(errors="replace")}


def parse(path: pathlib.Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        raise ValueError(f"{path}: missing front matter")
    _, fm, body = raw.split("---", 2)
    meta = {}
    for line in fm.strip().splitlines():
        line = line.split(" #", 1)[0].strip()
        if line and ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    doc = {"doc_id": meta["doc_id"], "title": meta["title"], "text": body.strip(),
           "audience": [a.strip() for a in meta.get("audience", "all").split(",") if a.strip()],
           "owner": meta.get("owner", "rick")}
    for k in ("source_url", "effective_date"):
        if meta.get(k):
            doc[k] = meta[k]
    return doc


def main(argv) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "load":
        files = []
        for p in map(pathlib.Path, argv[2:]):
            files += sorted(p.rglob("*.md")) if p.is_dir() else [p]
        failed = 0
        for f in files:
            res = _req("POST", "/admin/docs", parse(f))
            failed += "http_error" in res
            print(f"{f.name}: {json.dumps(res)}")
        return 1 if failed else 0
    if cmd == "retire" and len(argv) == 3:
        print(json.dumps(_req("POST", f"/admin/docs/{argv[2]}/retire")))
        return 0
    if cmd == "list":
        print(json.dumps(_req("GET", "/admin/docs"), indent=2))
        return 0
    if cmd == "stats":
        print(json.dumps(_req("GET", "/admin/stats"), indent=2))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
