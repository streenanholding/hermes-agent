#!/usr/bin/env python3
"""Draft quality gate (no_agent cron, every 5 min). Runs in every budget state.

The agent never posts a draft itself. It writes one Markdown file to
/opt/data/drafts/pending/. This script checks each pending draft and is the
only thing that posts drafts to Slack:

  pass -> printed as READY FOR RICK TO SEND, moved to drafts/posted/
  fail -> reasons printed, moved to drafts/failed/

Checks (CAPABILITIES.md, "Quality gate"):
  1. front matter: template, kind, tracker; template exists; its required
     `## ` headings are present in the draft
  2. no unfilled {{placeholders}}
  3. every line in a fact section carries [S#]; every [S#] is defined under
     ## Sources with a URL or tracker:<path> that exists
  4. no prohibited claims (quality/prohibited-claims.txt)
  5. no PHI or bank data patterns
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import agent2_common as c

PROHIBITED_FILE = c.DATA / "quality" / "prohibited-claims.txt"
FACT_SECTIONS = {"what we know", "facts used", "provider facts", "requirements", "costs"}
SOURCE_DEF_RE = re.compile(r"^\s*-\s*\[(S\d+)\]\s*(\S.*)$", re.M)
CITE_RE = re.compile(r"\[(S\d+)\]")

# PHI and bank data. NPI (10 digits) and TIN/EIN (NN-NNNNNNN) are allowed provider facts.
SENSITIVE = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("date of birth", re.compile(r"\b(dob|date of birth|birth ?date)\b", re.I)),
    ("member/subscriber ID", re.compile(r"\b(member|subscriber|policy) ?(id|number|#)\s*[:#]?\s*[A-Z0-9]{5,}", re.I)),
    ("patient identifier", re.compile(r"\bpatient(?:'s)? (name|id|dob|account)\b", re.I)),
    ("bank routing number", re.compile(r"\b(routing|aba|rtn)\b[^\n]{0,20}\b\d{9}\b", re.I)),
    ("bank account number", re.compile(r"\b(account|acct)\s*(no\.?|number|#)?\s*[:#]?\s*\d{6,17}\b", re.I)),
    ("card number", re.compile(r"\b(?:\d[ -]?){15,16}\b")),
]


def parse(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    meta = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip().strip('"')
    return meta, text[end + 4:].lstrip("\n")


def sections(body: str) -> dict[str, list[str]]:
    out, current = {}, None
    for line in body.splitlines():
        if line.startswith("## "):
            current = line[3:].strip().lower()
            out[current] = []
        elif current is not None:
            out[current].append(line)
    return out


def required_headings(template: Path) -> list[str]:
    _, body = parse(template.read_text())
    return [l[3:].strip() for l in body.splitlines() if l.startswith("## ")]


def prohibited_patterns() -> list[re.Pattern]:
    try:
        lines = PROHIBITED_FILE.read_text().splitlines()
    except OSError:
        return []
    return [re.compile(l, re.I) for l in lines if l.strip() and not l.lstrip().startswith("#")]


def check(path: Path) -> list[str]:
    text = path.read_text()
    meta, body = parse(text)
    problems: list[str] = []

    for field in ("template", "kind", "tracker"):
        if not meta.get(field):
            problems.append(f"front matter is missing `{field}`")
    template = c.TEMPLATES / "drafts" / meta.get("template", "")
    if meta.get("template") and not template.is_file():
        problems.append(f"template `{meta['template']}` is not an approved template")
    secs = sections(body)
    if template.is_file():
        for heading in required_headings(template):
            if heading.lower() not in secs:
                problems.append(f"missing section `## {heading}` required by the template")
    tracker = meta.get("tracker")
    if tracker and not (c.TRACKERS / tracker).is_file():
        problems.append(f"tracker `{tracker}` does not exist")

    if re.search(r"\{\{[^}]*\}\}", body):
        problems.append("unfilled {{placeholder}} left in the draft")

    defined = {}
    for sid, ref in SOURCE_DEF_RE.findall("\n".join(secs.get("sources", []))):
        defined[sid] = ref.strip()
    for sid, ref in defined.items():
        if ref.startswith("tracker:"):
            if not (c.TRACKERS / ref[len("tracker:"):].strip()).is_file():
                problems.append(f"source {sid} points to a tracker that does not exist")
        elif not re.match(r"https?://\S+", ref):
            problems.append(f"source {sid} is not a URL or tracker:<path>")
    for name, lines in secs.items():
        if name not in FACT_SECTIONS:
            continue
        for line in lines:
            s = line.strip()
            if not s or s.startswith(">"):
                continue
            if "NOT CONFIRMED" in s:
                continue  # an unknown is stated as unknown, no source needed
            cites = CITE_RE.findall(s)
            if not cites:
                problems.append(f"unsourced fact in `{name}`: {s[:80]}")
    for sid in set(CITE_RE.findall(body)):
        if sid not in defined:
            problems.append(f"[{sid}] is cited but not listed under ## Sources")

    for pat in prohibited_patterns():
        m = pat.search(body)
        if m:
            problems.append(f"prohibited claim: \"{m.group(0)}\"")
    for label, pat in SENSITIVE:
        if pat.search(body):
            problems.append(f"possible {label}: drafts may not contain patient or bank data")
    return problems


def move(path: Path, folder: str) -> None:
    dest = c.DRAFTS / folder
    dest.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(dest / path.name))


def main() -> int:
    pending = c.DRAFTS / "pending"
    if not pending.is_dir():
        return 0
    out = []
    passed = failed = 0
    for path in sorted(pending.glob("*.md")):
        problems = check(path)
        if problems:
            failed += 1
            out.append(f"*Draft failed the quality check:* `{path.name}`\n"
                       + "\n".join(f"• {p}" for p in problems)
                       + "\nFix it and queue a new file. Nothing was posted.")
            move(path, "failed")
        else:
            passed += 1
            _, body = parse(path.read_text())
            out.append(f"*READY FOR RICK TO SEND* (`{path.name}`, passed the quality check)\n\n{body.strip()}")
            move(path, "posted")
    if passed or failed:
        c.log_spend("draft_check", passed=passed, failed=failed)
        print("\n\n---\n\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
