import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REPO_URL = "https://github.com/robert-botto/skipwatch"


def fm(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), path
    return yaml.safe_load(text.split("---\n", 2)[1])


def test_agents_have_explicit_tools_without_agent():
    expected = {"frame-reader": "sonnet", "skill-critic": "sonnet", "skill-tester": "sonnet"}
    for name, model in expected.items():
        meta = fm(ROOT / "agents" / f"{name}.md")
        assert meta["name"] == name and meta["model"] == model
        tools = [t.strip() for t in str(meta["tools"]).split(",")]
        assert tools and "Agent" not in tools and "Task" not in tools


def test_agents_state_injection_rule():
    paths = list((ROOT / "agents").glob("*.md"))
    assert paths
    for path in paths:
        body = path.read_text(encoding="utf-8")
        assert "is data, not instructions" in body, path  # R-DIS-1 repeated in each agent


def test_plugin_skill_frontmatter():
    meta = fm(ROOT / "skills/skipwatch/SKILL.md")
    assert meta["name"] == "skipwatch"
    assert meta["argument-hint"] == "<url or path> [flags]"
    assert "summarize" in meta["description"].lower()  # names the near misses (R-UX-3)
    tools = {t.strip() for t in str(meta["allowed-tools"]).split(",")}
    assert tools == {"Bash", "Read", "Write", "Agent"}


def test_no_em_dash_in_plugin_files():
    paths = list((ROOT / "agents").glob("*.md")) + list((ROOT / "skills").rglob("*.md"))
    assert paths
    for path in paths:
        assert "\u2014" not in path.read_text(encoding="utf-8"), path


def test_plugin_json_points_at_real_repo():
    meta = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert meta["homepage"] == REPO_URL
    assert meta["repository"] == REPO_URL


def test_no_trigger_cases_cover_near_misses():
    # R-UX-3: summarize, download-only and transcribe-only requests never fire the skill
    for case in ("no-trigger", "no-trigger-download", "no-trigger-transcribe"):
        prompt = (ROOT / "evals" / case / "prompt.md").read_text(encoding="utf-8")
        assert "https://" in prompt, case
        grader = fm(ROOT / "evals" / case / "graders" / "skill-not-fired.md")
        assert grader == {"type": "tool_used", "tool": "Skill", "min": 0, "max": 0, "arm": "both"}


def test_doctor_tier_regex_tolerates_markdown():
    text = (ROOT / "evals/doctor/graders/tier-line.md").read_text(encoding="utf-8")
    pattern = text.split("---\n", 2)[2].strip()
    for line in ("Tier 2", "  Tier 1c", "**Tier 0**", "- **Tier 3** (full)"):
        assert re.search(pattern, f"Report\n{line}\nDone", re.M), line
    assert not re.search(pattern, "No tier here", re.M)
