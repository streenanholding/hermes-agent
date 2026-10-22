"""deploy/<agent>/AGENTS.md: required sections, order, size, shared reporting include."""

import importlib.util
import re
import sys
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"
AGENTS = ("sol", "carly", "seraphine", "carol")
SECTIONS = [  # (number, required words in the heading), in this exact order
    ("1", "Mission"), ("2", "Standing work loop"), ("3", "Decide"), ("4", "Ask first"), ("5", "Never"), ("6", "Reporting"),
]
MAX_LINES, MAX_CHARS = 100, 7000  # ~2 pages


def _render(agent):
    spec = importlib.util.spec_from_file_location("render_agents_md", DEPLOY / "common" / "render_agents_md.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.render(DEPLOY / agent / "AGENTS.md")


@pytest.mark.parametrize("agent", AGENTS)
def test_sections_in_exact_order(agent):
    headings = re.findall(r"^## (\d+)\. (.+)$", _render(agent), flags=re.M)
    assert [(n, next(w for _, w in SECTIONS if w.lower() in t.lower())) for n, t in headings][:6] == SECTIONS


@pytest.mark.parametrize("agent", AGENTS)
def test_under_two_pages(agent):
    text = _render(agent)
    assert len(text.splitlines()) <= MAX_LINES and len(text) <= MAX_CHARS


@pytest.mark.parametrize("agent", AGENTS)
def test_mission_is_two_sentences(agent):
    body = re.search(r"## 1\. Mission\n(.+?)\n\n", _render(agent), flags=re.S).group(1)
    assert len(re.findall(r"[.!?](?:\s|$)", body)) == 2


@pytest.mark.parametrize("agent", AGENTS)
def test_reporting_comes_from_the_single_shared_include(agent):
    src = (DEPLOY / agent / "AGENTS.md").read_text()
    assert "<!-- include: common/REPORTING.md -->" in src
    assert "three or more" not in src  # the rules live only in the shared include
    rendered, shared = _render(agent), (DEPLOY / "common" / "REPORTING.md").read_text().strip()
    assert shared in rendered
    for rule in ("#agent-log", "three or more", "Never post the same failure twice"):
        assert rule in shared


def test_bad_include_fails_loudly(tmp_path):
    spec = importlib.util.spec_from_file_location("r2", DEPLOY / "common" / "render_agents_md.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    f = tmp_path / "AGENTS.md"
    f.write_text("<!-- include: ../../etc/passwd -->\n")
    with pytest.raises(FileNotFoundError):
        mod.render(f)


def test_agent_specific_mandates():
    text = {a: _render(a) for a in AGENTS}
    assert "$20/month" in text["sol"] and "DRAFT" in text["sol"] and "Friday" in text["sol"] or "Fri 7:00" in text["sol"]
    assert "rick@finverified.ai" in text["sol"] and "ncoy@finverified.ai" in text["sol"]
    assert "$100 per 30 days" in text["carly"] and "Tue–Thu 10:00–2:00" in text["carly"] and "Never send email as Rick" in text["carly"]
    assert "Tier 1" in text["seraphine"] and "Better Stack" in text["seraphine"]
    assert "copying Rick and Nancy" in text["carol"] and "sincerely" in text["carol"]
