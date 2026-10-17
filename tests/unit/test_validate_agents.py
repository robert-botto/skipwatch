import json

import pytest
from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.models import Critique
from skipwatch.workdir import WorkDir

SKILL = """---
name: demo
description: Use when you want the demo.
---

# Demo

## Procedure

1. Install it. [spoken 00:05]
2. Run it. [spoken 00:10]
3. Check it. [inferred]
"""

SCORES = {
    "completeness": 8,
    "verifiability": 7,
    "actionability": 9,
    "trigger_quality": 6,
    "safety_hygiene": 10,
}


@pytest.fixture
def work(tmp_path):
    w = tmp_path / "w"
    WorkDir(w).ensure()  # directly in tmp_path, the test home's work/ (conftest)
    (w / "staging" / "demo").mkdir(parents=True)
    (w / "staging" / "demo" / "SKILL.md").write_text(SKILL, encoding="utf-8")
    return w


def write_critique(w, **overrides):
    data = {"schema": "skipwatch/critique/1", "scores": dict(SCORES), "score": 10, "fixes": []}
    data.update(overrides)
    (w / "critique.json").write_text(json.dumps(data), encoding="utf-8")


def critique(w):
    return CliRunner().invoke(
        app, ["validate-critique", "--work", str(w), "--skill", str(w / "staging" / "demo")]
    )


def test_validate_critique_rewrites_the_claimed_score_to_the_mean(work):
    write_critique(
        work,
        fixes=[
            {"step": 0, "timestamp": None, "fix": "Lead the description with a user phrase."},
            {"step": 3, "timestamp": "00:25", "fix": "Re-check the on-screen command at 00:25."},
        ],
    )
    r = critique(work)
    assert r.exit_code == 0, r.output
    assert "critique valid: score 8.0, 2 fixes" in r.output
    saved = Critique.model_validate_json((work / "critique.json").read_text(encoding="utf-8"))
    assert saved.score == 8.0 and len(saved.fixes) == 2


def test_validate_critique_rounds_the_mean_to_one_decimal(work):
    write_critique(work, scores=SCORES | {"safety_hygiene": 9})  # mean 7.8
    r = critique(work)
    assert r.exit_code == 0, r.output
    saved = Critique.model_validate_json((work / "critique.json").read_text(encoding="utf-8"))
    assert saved.score == 7.8


def test_validate_critique_missing_file_is_1(work):
    r = critique(work)
    assert r.exit_code == 1 and "critique.json" in r.output


def test_validate_critique_invalid_json_is_1(work):
    (work / "critique.json").write_text('{"schema": "skipwatch/critique/1"', encoding="utf-8")
    r = critique(work)
    assert r.exit_code == 1 and "critique.json invalid:" in r.output


def test_validate_critique_invalid_model_names_the_field(work):
    write_critique(work, fixes=[{"step": "two", "fix": "x"}])
    r = critique(work)
    assert r.exit_code == 1
    assert "critique.json invalid: fixes.0.step:" in r.output


def test_validate_critique_unknown_rubric_key_is_1(work):
    write_critique(work, scores=SCORES | {"vibes": 9})
    r = critique(work)
    assert r.exit_code == 1 and "critique.json invalid: scores.vibes" in r.output


@pytest.mark.parametrize("key", sorted(SCORES))
def test_validate_critique_missing_rubric_line_is_1(work, key):
    write_critique(work, scores={k: v for k, v in SCORES.items() if k != key})
    r = critique(work)
    assert r.exit_code == 1
    assert f"critique.json misses rubric line {key}" in r.output


@pytest.mark.parametrize("bad", [0, 0.5, 10.5, 11, -3])
def test_validate_critique_score_outside_1_to_10_is_1(work, bad):
    write_critique(work, scores=SCORES | {"actionability": bad})
    r = critique(work)
    assert r.exit_code == 1
    assert "actionability" in r.output and "1 to 10" in r.output


def test_validate_critique_fix_beyond_the_last_step_is_1(work):
    write_critique(work, fixes=[{"step": 4, "timestamp": None, "fix": "Add a step."}])
    r = critique(work)
    assert r.exit_code == 1 and "fix names step 4, the skill has 3" in r.output


def test_validate_critique_negative_fix_step_is_1(work):
    write_critique(work, fixes=[{"step": -1, "timestamp": None, "fix": "x"}])
    r = critique(work)
    assert r.exit_code == 1 and "fix names step -1, the skill has 3" in r.output


def test_validate_critique_more_than_8_fixes_is_1(work):
    fixes = [{"step": 1, "timestamp": None, "fix": f"fix {n}"} for n in range(9)]
    write_critique(work, fixes=fixes)
    r = critique(work)
    assert r.exit_code == 1 and "critique.json invalid: fixes:" in r.output


def test_validate_critique_failure_leaves_the_file_untouched(work):
    write_critique(work, scores=SCORES | {"actionability": 11})
    before = (work / "critique.json").read_bytes()
    assert critique(work).exit_code == 1
    assert (work / "critique.json").read_bytes() == before


def test_validate_critique_without_skill_md_is_7(work):
    (work / "staging" / "demo" / "SKILL.md").unlink()
    write_critique(work)
    r = critique(work)
    assert r.exit_code == 7 and "SKILL.md" in r.output


def write_report(w, data):
    (w / "test-report.json").write_text(json.dumps(data), encoding="utf-8")


def run_tester(w):
    return CliRunner().invoke(app, ["validate-test", "--work", str(w)])


@pytest.mark.parametrize(
    ("report", "line"),
    [
        ({"outcome": "completed", "task": "t"}, "Test run: completed"),
        (
            {"outcome": "blocked", "step": 3, "detail": "needs an account", "task": "t"},
            "Test run: blocked at step 3 (needs an account)",
        ),
        (
            {"outcome": "ambiguous", "step": 2, "detail": "which folder?", "task": "t"},
            "Test run: ambiguous at step 2 (which folder?)",
        ),
    ],
)
def test_validate_test_prints_exactly_one_line(work, report, line):
    write_report(work, {"schema": "skipwatch/test-report/1"} | report)
    r = run_tester(work)
    assert r.exit_code == 0, r.output
    assert r.stdout == line + "\n"


def test_validate_test_detail_newlines_stay_on_one_line(work):
    report = {"outcome": "blocked", "step": 1, "detail": "needs\nan account", "task": "t"}
    write_report(work, {"schema": "skipwatch/test-report/1"} | report)
    r = run_tester(work)
    assert r.stdout == "Test run: blocked at step 1 (needs an account)\n"


@pytest.mark.parametrize(
    "report",
    [
        {"outcome": "blocked", "task": "t"},  # no step, no detail
        {"outcome": "ambiguous", "step": 2, "detail": " ", "task": "t"},
        {"outcome": "finished", "task": "t"},
        {"outcome": "completed"},  # no task
        {"outcome": "blocked", "step": 0, "detail": "x", "task": "t"},
        {"outcome": "blocked", "step": 1, "detail": "x" * 501, "task": "t"},
    ],
)
def test_validate_test_invalid_report_is_1(work, report):
    write_report(work, {"schema": "skipwatch/test-report/1"} | report)
    r = run_tester(work)
    assert r.exit_code == 1 and "test-report.json invalid:" in r.output
    assert "Test run:" not in r.stdout


def test_validate_test_missing_report_is_1(work):
    r = run_tester(work)
    assert r.exit_code == 1 and "test-report.json" in r.output
