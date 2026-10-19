"""Drive, confined to the Pay✓erified shared drive (CAROL_DRIVE_ROOT_ID) and everything in it.

Every read and write first proves the file sits inside that drive. Carol may create
files and folders there and update only files she created herself. There is no
delete, move, rename or share function.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote, urlencode

from . import auth, common

_API = "https://www.googleapis.com/drive/v3"
_MAX_DEPTH = 15
_KINDS = {"doc": ("application/vnd.google-apps.document", "text/plain"),
          "sheet": ("application/vnd.google-apps.spreadsheet", "text/csv"),
          "text": ("text/plain", "text/plain")}
_MAX_ATTACH = 20 * 1024 * 1024


def root_id() -> str:
    return common.env_required("CAROL_DRIVE_ROOT_ID")


def _meta(file_id: str) -> Dict[str, Any]:
    return common.http_json("GET", f"{_API}/files/{quote(file_id, safe='')}?supportsAllDrives=true&fields=id,name,mimeType,parents,driveId,size,webViewLink",
                            headers=auth.headers())


def assert_in_root(file_id: str) -> Dict[str, Any]:
    root = root_id()
    if file_id == root:
        return {"id": root, "name": "Pay✓erified drive", "mimeType": "application/vnd.google-apps.folder"}
    first = None
    cur = file_id
    for _ in range(_MAX_DEPTH):
        m = _meta(cur)
        first = first or m
        if m.get("driveId") == root or cur == root:
            return first
        parents = m.get("parents") or []
        if not parents:
            break
        if parents[0] == root:
            return first
        cur = parents[0]
    raise common.PolicyError("Drive access refused: that file is outside the Pay✓erified drive")


def list_folder(folder_id: Optional[str] = None) -> Dict[str, Any]:
    fid = folder_id or root_id()
    assert_in_root(fid)
    q = urlencode({"q": f"'{fid}' in parents and trashed=false", "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
                   "corpora": "drive", "driveId": root_id(), "pageSize": 200,
                   "fields": "files(id,name,mimeType,modifiedTime,webViewLink)"})
    return common.http_json("GET", f"{_API}/files?{q}", headers=auth.headers())


def search(text: str) -> Dict[str, Any]:
    safe = text.replace("\\", "").replace("'", "\\'")
    q = urlencode({"q": f"(name contains '{safe}' or fullText contains '{safe}') and trashed=false", "supportsAllDrives": "true",
                   "includeItemsFromAllDrives": "true", "corpora": "drive", "driveId": root_id(), "pageSize": 50,
                   "fields": "files(id,name,mimeType,modifiedTime,webViewLink,parents)"})
    return common.http_json("GET", f"{_API}/files?{q}", headers=auth.headers())


def _docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf8", errors="replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    return re.sub(r"<[^>]+>", "", xml)


def read_text(file_id: str) -> Dict[str, Any]:
    meta = assert_in_root(file_id)
    mt = meta["mimeType"]
    if mt.startswith("application/vnd.google-apps"):
        mime = "text/csv" if "spreadsheet" in mt else "text/plain"
        text = common.http_bytes("GET", f"{_API}/files/{quote(file_id, safe='')}/export?mimeType={quote(mime)}", headers=auth.headers(), timeout=60).decode(errors="replace")
    else:
        data = common.http_bytes("GET", f"{_API}/files/{quote(file_id, safe='')}?alt=media&supportsAllDrives=true", headers=auth.headers(), timeout=60)
        if mt.endswith("wordprocessingml.document"):
            text = _docx_text(data)
        elif mt.startswith("text/") or mt in ("application/json", "text/csv"):
            text = data.decode(errors="replace")
        else:
            return {"name": meta["name"], "text": "", "note": f"{mt} can be attached to an email but not read as text"}
    return {"name": meta["name"], "text": text[:30000], "truncated": len(text) > 30000}


def fetch_attachment(file_id: str) -> Tuple[str, str, bytes]:
    """Return (filename, mime, bytes) for an email attachment. Google files export as PDF."""
    meta = assert_in_root(file_id)
    mt, name = meta["mimeType"], meta["name"]
    if mt == "application/vnd.google-apps.folder":
        raise common.PolicyError("cannot attach a folder")
    if mt.startswith("application/vnd.google-apps"):
        data = common.http_bytes("GET", f"{_API}/files/{quote(file_id, safe='')}/export?mimeType=application%2Fpdf", headers=auth.headers(), timeout=90)
        mt, name = "application/pdf", (name if name.lower().endswith(".pdf") else name + ".pdf")
    else:
        data = common.http_bytes("GET", f"{_API}/files/{quote(file_id, safe='')}?alt=media&supportsAllDrives=true", headers=auth.headers(), timeout=90)
    if len(data) > _MAX_ATTACH:
        raise common.PolicyError("attachment larger than 20 MB")
    return name, mt, data


def _mine() -> set:
    return set(common.load_state("drive_created.json", []))


def _remember(fid: str) -> None:
    ids = sorted(_mine() | {fid})
    common.save_state("drive_created.json", ids)


def create_folder(name: str, parent_id: str) -> Dict[str, Any]:
    assert_in_root(parent_id)
    r = common.http_json("POST", f"{_API}/files?supportsAllDrives=true&fields=id,name,webViewLink", headers=auth.headers(),
                         body={"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]})
    _remember(r["id"])
    return r


def _multipart(meta: Dict[str, Any], media_type: str, text: str) -> tuple:
    boundary = "carolbound7f3a"
    body = (f"--{boundary}\r\nContent-Type: application/json\r\n\r\n{json.dumps(meta)}\r\n--{boundary}\r\n"
            f"Content-Type: {media_type}\r\n\r\n{text}\r\n--{boundary}--").encode()
    return body, f"multipart/related; boundary={boundary}"


def create_file(name: str, parent_id: str, text: str, kind: str = "doc") -> Dict[str, Any]:
    """Create a NEW doc / sheet (from CSV) / text file inside the Pay✓erified drive."""
    assert_in_root(parent_id)
    if kind not in _KINDS:
        raise common.PolicyError("kind must be doc, sheet or text")
    target, media = _KINDS[kind]
    body, ctype = _multipart({"name": name, "parents": [parent_id], "mimeType": target}, media, text)
    raw = common.http_bytes("POST", "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true&fields=id,name,webViewLink",
                            headers={**auth.headers(), "Content-Type": ctype}, data=body, timeout=60)
    r = json.loads(raw.decode())
    _remember(r["id"])
    return r


def update_text(file_id: str, text: str) -> Dict[str, Any]:
    """Replace the content of a file Carol created herself. Other people's files are read-only to her."""
    assert_in_root(file_id)
    if file_id not in _mine():
        raise common.PolicyError("Carol can only update files she created. Create a new version instead of overwriting someone else's file.")
    mime = _meta(file_id)["mimeType"]
    media = "text/csv" if "spreadsheet" in mime else "text/plain"
    raw = common.http_bytes("PATCH", f"https://www.googleapis.com/upload/drive/v3/files/{quote(file_id, safe='')}?uploadType=media&supportsAllDrives=true&fields=id,name,webViewLink",
                            headers={**auth.headers(), "Content-Type": media}, data=text.encode(), timeout=60)
    return json.loads(raw.decode())
