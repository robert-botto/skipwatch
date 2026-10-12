"""tests/fixtures/critic-work: a work folder paused before the critic, one planted flaw (issue 19).

Built by scripts/make_critic_fixture.py; eval critic-repair resumes it. Offline, no ffmpeg.
"""

import json
import re
import shutil
from pathlib import Path

from skipwatch.checks.runner import run_all
from skipwatch.skillmd import parse
from skipwatch.workdir import STAGE_ORDER

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tests" / "fixtures" / "critic-work"
NAME = "run-skipdemo-tutorial"
PROMPT = "Write a four line poem about rivers"
TEXT_SUFFIXES = (".json", ".md")


def _texts() -> dict[str, str]:
    return {
        p.relative_to(WORK).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(WORK.rglob("*"))
        if p.is_file() and p.suffix in TEXT_SUFFIXES
    }


def test_stages_done_through_distill_and_critique_pending():
    stages = json.loads((WORK / "stages.json").read_text(encoding="utf-8"))["stages"]
    done = STAGE_ORDER[: STAGE_ORDER.index("critique")]
    assert all(stages[name]["status"] == "done" for name in done)
    assert all(stages[name]["status"] == "pending" for name in STAGE_ORDER if name not in done)
    assert not (WORK / "critique.json").exists() and not (WORK / "check-report.json").exists()


def test_step_2_is_planted_inferred_while_the_evidence_shows_it_at_00_25():
    skill = (WORK / "staging" / NAME / "SKILL.md").read_text(encoding="utf-8")
    step2 = parse(skill).steps[1]
    assert step2.number == 2 and [t.kind for t in step2.tags] == ["inferred"]
    assert "[on-screen 00:25]" not in skill and PROMPT not in skill
    assert re.search(r"(?m)^- Step 2: ", parse(skill).section_text("Unverified and gaps"))
    draft = (WORK / "draft" / "SKILL.md").read_text(encoding="utf-8")  # raw: the key unredacted
    assert [t.kind for t in parse(draft).steps[1].tags] == ["inferred"] and PROMPT not in draft
    outline = (WORK / "outline.md").read_text(encoding="utf-8")
    assert f'[on-screen 00:25] | verbatim: "{PROMPT}" (f000250)' in outline
    notes = json.loads((WORK / "notes" / "batch-01.json").read_text(encoding="utf-8"))
    at_25 = [f for f in notes["frames"] if f["t"] == 25.0]
    assert [v["text"] for f in at_25 for v in f["verbatim"]] == [PROMPT]
    assert (WORK / "frames" / "f000250.jpg").is_file()


def test_run_json_resumes_with_yes_to_and_name_under_the_cwd_token():
    run = json.loads((WORK / "run.json").read_text(encoding="utf-8"))
    assert run["input"] == "__CWD__/tutorial-60s.mp4"
    assert run["flags"] == ["--yes", "--to", "__CWD__/installed", "--name", NAME]
    ingest = json.loads((WORK / "ingest.json").read_text(encoding="utf-8"))
    assert ingest["media"]["path"] == "__CWD__/tutorial-60s.mp4"


def test_no_absolute_paths_or_secrets_outside_quoted_evidence():
    for rel, text in _texts().items():
        assert not re.search(r"/(?:Users|home|private|var/folders|tmp)/", text), rel
        assert "—" not in text, rel
        if rel.startswith(("staging/", "draft/")) or rel.startswith("notes/"):
            continue
        assert "FIXTURE0NLY" not in text or rel == "outline.md", rel


def test_the_planted_flaw_passes_check(tmp_path, monkeypatch):
    """Only the critic can find it: check alone passes the draft as it is."""
    monkeypatch.setenv("SKIPWATCH_HOME", str(tmp_path / "home"))
    work = tmp_path / "work"
    shutil.copytree(WORK, work)
    for path in (work / "ingest.json", work / "run.json"):
        path.write_text(path.read_text(encoding="utf-8").replace("__CWD__", str(tmp_path)))
    report = run_all(work / "staging" / NAME, work)
    assert report.passed, [i for r in report.results for i in r.items]
