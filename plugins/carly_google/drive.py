"""Drive, confined to the Carly folder (CARLY_DRIVE_FOLDER_ID) and everything under it.

Every read and write first proves the file sits inside that folder. There is no
delete, move, rename or share function.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional
from urllib.parse import quote, urlencode

from . import auth, common

_API = "https://www.googleapis.com/drive/v3"
_MAX_DEPTH = 12
_KINDS = {"doc": ("application/vnd.google-apps.document", "text/plain"),
          "sheet": ("application/vnd.google-apps.spreadsheet", "text/csv"),
          "text": ("text/plain", "text/plain")}


def root_id() -> str:
    return common.env_required("CARLY_DRIVE_FOLDER_ID")


def _meta(file_id: str) -> Dict[str, Any]:
    return common.http_json("GET", f"{_API}/files/{quote(file_id, safe='')}?supportsAllDrives=true&fields=id,name,mimeType,parents",
                            headers=auth.headers())


def assert_in_root(file_id: str) -> None:
    root = root_id()
    cur = file_id
    for _ in range(_MAX_DEPTH):
        if cur == root:
            return
        parents = _meta(cur).get("parents") or []
        if not parents:
            break
        cur = parents[0]
    raise common.PolicyError("Drive access refused: that file is outside the Carly folder")


def list_folder(folder_id: Optional[str] = None) -> Dict[str, Any]:
    fid = folder_id or root_id()
    assert_in_root(fid)
    q = urlencode({"q": f"'{fid}' in parents and trashed=false", "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
                   "pageSize": 200, "fields": "files(id,name,mimeType,modifiedTime,webViewLink)"})
    return common.http_json("GET", f"{_API}/files?{q}", headers=auth.headers())


def read_text(file_id: str) -> Dict[str, Any]:
    assert_in_root(file_id)
    meta = _meta(file_id)
    if meta["mimeType"].startswith("application/vnd.google-apps"):
        mime = "text/csv" if "spreadsheet" in meta["mimeType"] else "text/plain"
        url = f"{_API}/files/{quote(file_id, safe='')}/export?mimeType={quote(mime)}"
    else:
        url = f"{_API}/files/{quote(file_id, safe='')}?alt=media&supportsAllDrives=true"
    text = common.http_bytes("GET", url, headers=auth.headers(), timeout=60).decode(errors="replace")
    return {"name": meta["name"], "text": text[:20000], "truncated": len(text) > 20000}


def create_folder(name: str, parent_id: str) -> Dict[str, Any]:
    assert_in_root(parent_id)
    return common.http_json("POST", f"{_API}/files?supportsAllDrives=true&fields=id,name,webViewLink", headers=auth.headers(),
                            body={"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]})


def _multipart(meta: Dict[str, Any], media_type: str, text: str) -> tuple[bytes, str]:
    boundary = "carlybound7f3a"
    body = (f"--{boundary}\r\nContent-Type: application/json\r\n\r\n{json.dumps(meta)}\r\n--{boundary}\r\n"
            f"Content-Type: {media_type}\r\n\r\n{text}\r\n--{boundary}--").encode()
    return body, f"multipart/related; boundary={boundary}"


def create_file(name: str, parent_id: str, text: str, kind: str = "doc") -> Dict[str, Any]:
    """Create a NEW doc / sheet (from CSV) / text file inside the Carly folder."""
    assert_in_root(parent_id)
    if kind not in _KINDS:
        raise common.PolicyError("kind must be doc, sheet or text")
    target, media = _KINDS[kind]
    body, ctype = _multipart({"name": name, "parents": [parent_id], "mimeType": target}, media, text)
    raw = common.http_bytes("POST", "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true&fields=id,name,webViewLink",
                            headers={**auth.headers(), "Content-Type": ctype}, data=body, timeout=60)
    return json.loads(raw.decode())


def update_text(file_id: str, text: str) -> Dict[str, Any]:
    """Replace the content of an existing tracker (doc / sheet CSV / text) inside the Carly folder."""
    assert_in_root(file_id)
    mime = _meta(file_id)["mimeType"]
    media = "text/csv" if "spreadsheet" in mime else "text/plain"
    raw = common.http_bytes("PATCH", f"https://www.googleapis.com/upload/drive/v3/files/{quote(file_id, safe='')}?uploadType=media&supportsAllDrives=true&fields=id,name,webViewLink",
                            headers={**auth.headers(), "Content-Type": media}, data=text.encode(), timeout=60)
    return json.loads(raw.decode())
