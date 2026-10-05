"""Google Drive via service account. Create-only in "FinVerified Finance"; read-only on Treasury.

There is deliberately no delete, rename, move, or update function here. Writes are
checked against the Finance shared drive id before any request is made.
"""

from __future__ import annotations

import base64
import json
import os
import time
from typing import Any, Dict, Optional
from urllib.parse import quote, urlencode

from . import common

FINANCE = "FinVerified Finance"
TREASURY = "FinVerified Treasury (Locked)"
_API = "https://www.googleapis.com/drive/v3"


class DrivePolicyError(PermissionError):
    pass


def _b64(b: bytes) -> bytes:
    return base64.urlsafe_b64encode(b).rstrip(b"=")


def _token() -> str:
    cached = common.load_state("drive_token.json", {})
    if cached.get("expires_at", 0) > time.time():
        return cached["access_token"]
    sa = json.loads(os.environ["GOOGLE_SOL_SA_JSON"])
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    now = int(time.time())
    head = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = _b64(json.dumps({"iss": sa["client_email"], "scope": "https://www.googleapis.com/auth/drive",
                              "aud": "https://oauth2.googleapis.com/token", "iat": now, "exp": now + 3600}).encode())
    key = serialization.load_pem_private_key(sa["private_key"].encode(), password=None)
    sig = _b64(key.sign(head + b"." + claims, padding.PKCS1v15(), hashes.SHA256()))
    tok = common.http_json("POST", "https://oauth2.googleapis.com/token",
                           form={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                 "assertion": (head + b"." + claims + b"." + sig).decode()})
    tok["expires_at"] = time.time() + int(tok.get("expires_in", 3600)) - 60
    common.save_state("drive_token.json", tok)
    return tok["access_token"]


def _h() -> Dict[str, str]:
    return {"Authorization": "Bearer " + _token()}


def shared_drives() -> Dict[str, str]:
    r = common.http_json("GET", f"{_API}/drives?pageSize=100", headers=_h())
    return {d["name"]: d["id"] for d in r.get("drives", [])}


def assert_writable(drive_id: str, drives: Optional[Dict[str, str]] = None) -> None:
    drives = drives if drives is not None else shared_drives()
    if drive_id == drives.get(TREASURY) or drive_id != drives.get(FINANCE):
        raise DrivePolicyError("Drive write rejected: only the FinVerified Finance drive is writable; Treasury is read-only")


def list_folder(folder_id: str) -> Dict[str, Any]:
    q = urlencode({"q": f"'{folder_id}' in parents and trashed=false", "supportsAllDrives": "true",
                   "includeItemsFromAllDrives": "true", "pageSize": 200,
                   "fields": "files(id,name,mimeType,modifiedTime,driveId,webViewLink)"})
    return common.http_json("GET", f"{_API}/files?{q}", headers=_h())


def read_text(file_id: str) -> str:
    import urllib.request
    meta = common.http_json("GET", f"{_API}/files/{file_id}?supportsAllDrives=true&fields=mimeType,name", headers=_h())
    if meta["mimeType"].startswith("application/vnd.google-apps"):
        url = f"{_API}/files/{file_id}/export?mimeType=" + quote("text/csv" if "spreadsheet" in meta["mimeType"] else "text/plain")
    else:
        url = f"{_API}/files/{file_id}?alt=media&supportsAllDrives=true"
    req = urllib.request.Request(url, headers=_h())
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode(errors="replace")


def create_folder(name: str, parent_id: str) -> Dict[str, Any]:
    p = common.http_json("GET", f"{_API}/files/{parent_id}?supportsAllDrives=true&fields=driveId", headers=_h())
    assert_writable(p.get("driveId", ""))
    return common.http_json("POST", f"{_API}/files?supportsAllDrives=true&fields=id,name,webViewLink", headers=_h(),
                            body={"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]})


def create_sheet_from_csv(name: str, parent_id: str, csv_text: str) -> Dict[str, Any]:
    """Create a NEW Google Sheet from CSV in a Finance folder. Never modifies an existing file."""
    import urllib.request
    p = common.http_json("GET", f"{_API}/files/{parent_id}?supportsAllDrives=true&fields=driveId", headers=_h())
    assert_writable(p.get("driveId", ""))
    boundary = "solbound"
    meta = json.dumps({"name": name, "parents": [parent_id], "mimeType": "application/vnd.google-apps.spreadsheet"})
    body = (f"--{boundary}\r\nContent-Type: application/json\r\n\r\n{meta}\r\n--{boundary}\r\n"
            f"Content-Type: text/csv\r\n\r\n{csv_text}\r\n--{boundary}--").encode()
    req = urllib.request.Request(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true&fields=id,name,webViewLink",
        data=body, method="POST", headers={**_h(), "Content-Type": f"multipart/related; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())
