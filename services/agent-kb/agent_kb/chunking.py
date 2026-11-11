"""Split a document into ~500-token passages (about 1,800 characters) with a small overlap."""

from __future__ import annotations

import re
from typing import List

MAX_CHARS = 1800
OVERLAP_CHARS = 200


def chunk(text: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP_CHARS) -> List[str]:
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out: List[str] = []
    cur = ""
    for p in paras:
        # A single oversized paragraph is hard-split on sentence or word boundaries.
        while len(p) > max_chars:
            cut = p.rfind(". ", 0, max_chars)
            cut = cut + 1 if cut > max_chars // 2 else p.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            piece, p = p[:cut].strip(), p[cut:].strip()
            if cur:
                out.append(cur)
                cur = ""
            out.append(piece)
        if cur and len(cur) + 2 + len(p) > max_chars:
            out.append(cur)
            tail = cur[-overlap:]
            sp = tail.find(" ")
            cur = (tail[sp + 1:] if sp >= 0 else tail) + "\n\n" + p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        out.append(cur)
    return out
