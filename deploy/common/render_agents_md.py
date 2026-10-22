#!/usr/bin/env python3
"""Render an agent's AGENTS.md by resolving ``<!-- include: path -->`` lines.

Include paths are relative to ``deploy/`` (e.g. ``common/REPORTING.md``), so
shared sections live in one place. Usage: render_agents_md.py SRC [DEST]
(DEST omitted = stdout). Fails loudly on a missing include.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parent.parent
INCLUDE = re.compile(r"^<!--\s*include:\s*(\S+)\s*-->\s*$")


def render(src: Path) -> str:
    out = []
    for line in src.read_text().splitlines():
        m = INCLUDE.match(line)
        if not m:
            out.append(line)
            continue
        target = (DEPLOY_DIR / m.group(1)).resolve()
        if DEPLOY_DIR not in target.parents or not target.is_file():
            raise FileNotFoundError(f"{src}: bad include {m.group(1)!r}")
        out.append(target.read_text().rstrip())
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    if not 1 <= len(argv) <= 2:
        print(__doc__, file=sys.stderr)
        return 2
    text = render(Path(argv[0]))
    if len(argv) == 2:
        Path(argv[1]).write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
