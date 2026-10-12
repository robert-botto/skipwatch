"""`review`: the engine prints the whole review screen (review-screen.md, skill audit 3 fix 6).

Golden screens are the spec's own examples; the edge cases change one input each.
"""

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from skipwatch.checks.runner import run_all
from skipwatch.cli import app
from skipwatch.errors import ExitCode
from skipwatch.pack import pack_skill, unpack

from ._skills import installed_skill

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
NAME = "run-skipdemo-tutorial"
GOOD_PACK = FIXTURES / "packs" / f"{NAME}.skillpack.zip"
TRIGGERS = (
    '  Triggers: "initialise a skipdemo project", "run the skipdemo tutorial", '
    '"set up skipdemo with a prompt"'
)
INFERRED_STEP_2 = (
    "   Expected: a short poem. [on-screen 00:25]",
    "   Expected: a short poem. [inferred]",
)


def run_case(tmp_path: Path, edit_skill=None) -> tuple[Path, Path]:
    """The fixture run (tests/fixtures/skills), checked: work/staging/<name>/ plus reports."""
    work = tmp_path / "work"
    shutil.copytree(FIXTURES / "skills" / "work", work)
    staging = work / "staging" / NAME
    shutil.copytree(FIXTURES / "skills" / "good" / NAME, staging)
    frame = staging / "assets" / "frames" / "f000250.jpg"
    frame.parent.mkdir(parents=True)
    Image.new("RGB", (960, 540), (30, 30, 30)).save(frame, "JPEG")
    if edit_skill is not None:
        skill_md = staging / "SKILL.md"
        skill_md.write_text(edit_skill(skill_md.read_text(encoding="utf-8")), encoding="utf-8")
    run_all(staging, work)
    return work, staging


def review(work: Path, skill: Path, *extra: str):
    return CliRunner().invoke(app, ["review", "--work", str(work), "--skill", str(skill), *extra])


def screen_of(work: Path, skill: Path, *extra: str) -> str:
    r = review(work, skill, *extra)
    assert r.exit_code == 0, r.output
    return r.stdout


def lines_of(work: Path, skill: Path, *extra: str) -> list[str]:
    return screen_of(work, skill, *extra).splitlines()


def line(lines: list[str], prefix: str) -> str:
    found = [x for x in lines if x.startswith("  " + prefix)]
    assert len(found) == 1, lines
    return found[0]


def edit_json(path: Path, **updates) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(updates)
    path.write_text(json.dumps(data), encoding="utf-8")


def draft(staging: Path) -> str:
    return str(staging.absolute()) + os.sep


# ---- golden screens ----


def test_run_screen_is_the_spec_example(tmp_path):
    work, staging = run_case(tmp_path)
    assert screen_of(work, staging) == "\n".join(
        [
            f"Skill ready for review: {NAME}",
            TRIGGERS,
            "  Steps: 4 (1 spoken, 3 on-screen, 0 written, 0 inferred), 0 gaps",
            "  Unverified: none",
            "  Unread frames: none",
            "  Safety flags: none",
            "  Confidence: medium (critic not run)",
            '  Source: "tutorial-60s" by local file, undated',
            "  Provider calls: none (free route)",
            f"  Draft: {draft(staging)}",
            "",
        ]
    )


def test_pack_screen_from_the_committed_pack(sw_home):
    result = unpack(GOOD_PACK, None)
    work, staging = Path(result.work), Path(result.staging)
    run_all(staging, work)
    sha = hashlib.sha256(GOOD_PACK.read_bytes()).hexdigest()[:12]
    assert screen_of(work, staging) == "\n".join(
        [
            f"Skill ready for review: {NAME}",
            TRIGGERS,
            "  Steps: 4 (1 spoken, 3 on-screen, 0 written, 0 inferred), 0 gaps",
            "  Unverified: 3 quoted steps not re-verified (shared pack)",
            "  Unread frames: none",
            "  Safety flags: none",
            "  Confidence: medium (shared pack: critic not re-run here; the pack claims medium, "
            "critic none)",
            '  Source: "tutorial-60s" by local file, undated '
            f"(from pack {NAME}.skillpack.zip, sha256 {sha})",
            "  Provider calls: none (shared pack)",
            f"  Draft: {draft(staging)}",
            "",
        ]
    )


def test_pack_that_claims_high_names_the_claim_and_critic_score(tmp_path, sw_home):
    skill = installed_skill(tmp_path)  # claims high, critic 8.5
    packed = pack_skill(skill, tmp_path / "run-x.skillpack.zip")
    result = unpack(Path(packed.path), None)
    work, staging = Path(result.work), Path(result.staging)
    report = run_all(staging, work)
    lines = lines_of(work, staging, "--unread", "f000100 (reader failed twice)")
    assert line(lines, "Confidence:") == (
        f"  Confidence: {report.pack_confidence} (shared pack: critic not re-run here; "
        "the pack claims high, critic 8.5)"
    )
    assert line(lines, "Unread frames:") == "  Unread frames: none"  # never for a pack
    assert line(lines, "Source:") == (
        '  Source: "Run x" by someone, undated (from pack run-x.skillpack.zip, sha256 '
        f"{hashlib.sha256(Path(packed.path).read_bytes()).hexdigest()[:12]})"
    )


def test_pack_other_reasons_follow_after_a_semicolon(sw_home):
    result = unpack(GOOD_PACK, None)
    work, staging = Path(result.work), Path(result.staging)
    run_all(staging, work)
    (work / "transcript.json").unlink()
    assert line(lines_of(work, staging), "Confidence:") == (
        "  Confidence: medium (shared pack: critic not re-run here; the pack claims medium, "
        "critic none; no transcript)"
    )


# ---- extra lines ----


def test_extra_lines_follow_draft_in_spec_order(tmp_path):
    work, staging = run_case(tmp_path)
    note = "video came from a linked post: https://x.com/other/status/2"
    edit_json(work / "ingest.json", notes=["something else", note], fetched_with_cookies=True)
    transcript = work / "transcript.json"
    edit_json(
        transcript,
        cross_check={"origin": "treg:x.transcript", "text": "zzz qqq", "similarity": 0.1234},
    )
    lines = lines_of(work, staging)
    assert lines[-5:] == [
        f"  Draft: {draft(staging)}",
        f"  {note}",
        "  Fetched with your browser cookies: this skill cannot be packed for sharing.",
        "  Cross-check: 0.12 against treg:x.transcript",
        "  transcript sources disagree: 0.12",
    ]


def test_agreeing_cross_check_has_no_disagreement_line(tmp_path):
    work, staging = run_case(tmp_path)
    segments = json.loads((work / "transcript.json").read_text(encoding="utf-8"))["segments"]
    text = " ".join(s["text"] for s in segments)
    edit_json(
        work / "transcript.json",
        cross_check={"origin": "treg:x.transcript", "text": text, "similarity": 0.956},
    )
    lines = lines_of(work, staging)
    assert lines[-1] == "  Cross-check: 0.96 against treg:x.transcript"
    assert not any("disagree" in x for x in lines)


def test_linked_post_from_an_older_cache_is_read_from_route_fallbacks(tmp_path):
    work, staging = run_case(tmp_path)
    note = "video came from a linked post: https://x.com/other/status/3"
    ingest = json.loads((work / "ingest.json").read_text(encoding="utf-8"))
    ingest["route"]["fallbacks"] = ["x: other", note]
    (work / "ingest.json").write_text(json.dumps(ingest), encoding="utf-8")
    assert lines_of(work, staging)[-1] == f"  {note}"


# ---- line sources ----


def test_provider_calls_line_is_copied_exactly_from_check_report(tmp_path):
    work, staging = run_case(tmp_path)
    treg = "treg: 2 calls, $0.0043 (x.thread $0.0038, x.comments $0.0005)"
    edit_json(work / "check-report.json", provider_calls_line=treg)
    assert line(lines_of(work, staging), "Provider calls:") == f"  Provider calls: {treg}"


def test_cached_transcript_adds_its_origin(tmp_path):
    work, staging = run_case(tmp_path)
    (work / "logs").mkdir()
    (work / "logs" / "transcribe.log").write_text(
        "Transcribe: reused cached transcript (captions, 3h old)\n", encoding="utf-8"
    )
    assert line(lines_of(work, staging), "Provider calls:") == (
        "  Provider calls: none (free route); transcript cached (captions)"
    )


def test_cloud_transcription_names_the_billed_key(tmp_path):
    work, staging = run_case(tmp_path)
    edit_json(work / "transcript.json", origin="groq")
    assert line(lines_of(work, staging), "Provider calls:") == (
        "  Provider calls: none (free route); groq transcription (billed to your GROQ_API_KEY key)"
    )


def test_source_with_author_and_date(tmp_path):
    work, staging = run_case(tmp_path)
    ingest = json.loads((work / "ingest.json").read_text(encoding="utf-8"))
    ingest["source"].update(
        kind="video",
        platform="x",
        url="https://x.com/someone/status/1",
        author="@someone",
        title="Deep partials",
        posted_at="2022-03-21T10:00:00Z",
    )
    (work / "ingest.json").write_text(json.dumps(ingest), encoding="utf-8")
    assert line(lines_of(work, staging), "Source:") == (
        '  Source: "Deep partials" by @someone, 2022-03-21'
    )


def test_safety_flags_name_kind_severity_and_step(tmp_path):
    work, staging = run_case(tmp_path)
    report = json.loads((work / "check-report.json").read_text(encoding="utf-8"))
    for result in report["results"]:
        if result["check"] == "safety":
            result["flags"] = [
                {"step": 7, "kind": "pipe_to_shell", "text": "curl x | sh", "severity": "high"},
                {"step": None, "kind": "sudo", "text": "sudo rm", "severity": "medium"},
            ]
    (work / "check-report.json").write_text(json.dumps(report), encoding="utf-8")
    assert line(lines_of(work, staging), "Safety flags:") == (
        "  Safety flags: pipe_to_shell (high) at step 7, sudo (medium)"
    )


def test_inferred_steps_and_degradations_fill_unverified(tmp_path):
    def infer_step_2(text: str) -> str:
        text = text.replace(*INFERRED_STEP_2)
        return text.replace(
            "## Unverified and gaps\n\nNone.",
            "## Unverified and gaps\n\n- Step 2: the prompt text was not captured.",
        )

    work, staging = run_case(tmp_path, infer_step_2)
    moved = "work folder moved into the project (/p/.skipwatch): home folder not writable"
    lines = lines_of(work, staging, "--degradation", moved, "--degradation", "no transcript")
    assert line(lines, "Unverified:") == (
        f"  Unverified: step 2 (the prompt text was not captured); {moved}; no transcript"
    )
    assert line(lines, "Steps:") == (
        "  Steps: 4 (1 spoken, 2 on-screen, 0 written, 1 inferred), 0 gaps"
    )


def test_unread_frames_are_listed_and_become_a_confidence_reason(tmp_path):
    work, staging = run_case(tmp_path)
    lines = lines_of(
        work,
        staging,
        "--unread",
        "f006032 (reader failed twice)",
        "--unread",
        "f006040 (reader failed twice; may hold a step)",
    )
    assert line(lines, "Unread frames:") == (
        "  Unread frames: f006032 (reader failed twice), "
        "f006040 (reader failed twice; may hold a step)"
    )
    assert line(lines, "Confidence:") == "  Confidence: medium (critic not run; frames unread)"


def test_critic_failed_twice_replaces_critic_not_run(tmp_path):
    work, staging = run_case(tmp_path)
    lines = lines_of(work, staging, "--degradation", "critic failed twice")
    assert line(lines, "Confidence:") == "  Confidence: medium (critic failed twice)"
    assert line(lines, "Unverified:") == "  Unverified: critic failed twice"


def test_low_critic_score_gaps_and_no_transcript_are_reasons(tmp_path):
    work, staging = run_case(tmp_path)
    edit_json(staging / "skipwatch.json", critic_score=6.3, confidence="low")
    report = json.loads((work / "check-report.json").read_text(encoding="utf-8"))
    report["counts"]["gaps"] = 2
    (work / "check-report.json").write_text(json.dumps(report), encoding="utf-8")
    (work / "transcript.json").unlink()
    lines = lines_of(work, staging)
    assert line(lines, "Confidence:") == (
        "  Confidence: low (critic score 6.3; 2 gaps; no transcript)"
    )
    assert line(lines, "Steps:").endswith(", 2 gaps")


def test_one_gap_is_singular(tmp_path):
    work, staging = run_case(tmp_path)
    report = json.loads((work / "check-report.json").read_text(encoding="utf-8"))
    report["counts"]["gaps"] = 1
    (work / "check-report.json").write_text(json.dumps(report), encoding="utf-8")
    lines = lines_of(work, staging)
    assert line(lines, "Steps:").endswith(", 1 gap")
    assert line(lines, "Confidence:") == "  Confidence: medium (critic not run; 1 gap)"


def test_high_confidence_has_no_reason(tmp_path):
    work, staging = run_case(tmp_path)
    edit_json(staging / "skipwatch.json", critic_score=8.5, confidence="high")
    assert line(lines_of(work, staging), "Confidence:") == "  Confidence: high"


def test_test_run_line_goes_directly_after_confidence(tmp_path):
    work, staging = run_case(tmp_path)
    lines = lines_of(work, staging, "--test-run", "Test run: blocked at step 2 (needs a key)")
    at = lines.index("  Confidence: medium (critic not run)")
    assert lines[at + 1] == "  Test run: blocked at step 2 (needs a key)"


def test_test_run_must_be_the_validate_test_line(tmp_path):
    work, staging = run_case(tmp_path)
    r = review(work, staging, "--test-run", "completed")
    assert r.exit_code == ExitCode.USAGE
    assert r.stdout == ""


def test_json_wraps_the_same_screen(tmp_path):
    work, staging = run_case(tmp_path)
    plain = screen_of(work, staging)
    assert json.loads(screen_of(work, staging, "--json")) == {"screen": plain}


# ---- missing inputs ----


@pytest.mark.parametrize(
    ("folder", "name"),
    [
        ("work", "check-report.json"),
        ("work", "ingest.json"),
        ("skill", "skipwatch.json"),
        ("skill", "SKILL.md"),
    ],
)
def test_missing_required_input_is_exit_7_naming_it(tmp_path, folder, name):
    work, staging = run_case(tmp_path)
    missing = (work if folder == "work" else staging) / name
    missing.unlink()
    r = review(work, staging)
    assert r.exit_code == ExitCode.NO_CONTENT == 7
    assert str(missing) in r.output
    assert r.stdout == ""


def test_invalid_required_input_is_exit_7(tmp_path):
    work, staging = run_case(tmp_path)
    (work / "check-report.json").write_text("{}", encoding="utf-8")
    r = review(work, staging)
    assert r.exit_code == 7 and "check-report.json" in r.output


def test_check_report_without_a_provider_calls_line_is_exit_7(tmp_path):
    work, staging = run_case(tmp_path)
    edit_json(work / "check-report.json", provider_calls_line=None)
    r = review(work, staging)
    assert r.exit_code == 7 and "provider_calls_line" in r.output


def test_high_confidence_prints_no_reasons_even_when_some_apply(tmp_path):
    work, staging = run_case(tmp_path)
    edit_json(staging / "skipwatch.json", critic_score=8.5, confidence="high")
    (work / "transcript.json").unlink()
    lines = lines_of(work, staging, "--unread", "f006032 (reader failed twice)")
    assert line(lines, "Confidence:") == "  Confidence: high"


def test_noted_degradations_and_unread_frames_reach_the_screen(tmp_path):
    from skipwatch.workdir import WorkDir

    work, staging = run_case(tmp_path)
    WorkDir(work).ensure()  # note needs a work folder's stages.json
    for args in (
        ("--degradation", "critic failed twice"),
        ("--unread", "f006032 (reader failed twice)"),
    ):
        r = CliRunner().invoke(app, ["note", "--work", str(work), *args])
        assert r.exit_code == 0, r.output
    lines = lines_of(work, staging)
    assert line(lines, "Confidence:") == "  Confidence: medium (critic failed twice; frames unread)"
    assert line(lines, "Unread frames:") == "  Unread frames: f006032 (reader failed twice)"


def test_noted_items_come_first_and_command_line_repeats_are_dropped(tmp_path):
    from skipwatch.models import DegradationsFile
    from skipwatch.workdir import write_model

    work, staging = run_case(tmp_path)
    noted = DegradationsFile(
        degradations=["no transcript"], unread=["f000100 (reader failed twice)"]
    )
    write_model(work / "degradations.json", noted)
    lines = lines_of(
        work,
        staging,
        "--degradation",
        "test run failed twice",
        "--degradation",
        "no transcript",
        "--unread",
        "f000200 (reader failed twice)",
        "--unread",
        "f000100 (reader failed twice)",
    )
    assert line(lines, "Unverified:") == "  Unverified: no transcript; test run failed twice"
    assert line(lines, "Unread frames:") == (
        "  Unread frames: f000100 (reader failed twice), f000200 (reader failed twice)"
    )


def test_an_invalid_degradations_file_is_exit_7_naming_it(tmp_path):
    work, staging = run_case(tmp_path)
    (work / "degradations.json").write_text("{not json", encoding="utf-8")
    r = review(work, staging)
    assert r.exit_code == ExitCode.NO_CONTENT
    assert "degradations.json" in r.stderr and "delete" in r.stderr
