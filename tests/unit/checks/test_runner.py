import json

from typer.testing import CliRunner

from skipwatch.checks import CHECK_ORDER
from skipwatch.cli import app
from skipwatch.models import CheckReport, Counts, Manifest
from skipwatch.workdir import read_model
from tests.unit.checks.conftest import KEY, NAME, hardlink_or_skip, make_case


def _check(staging, work, *extra):
    return CliRunner().invoke(app, ["check", str(staging), "--work", str(work), *extra])


def test_check_exit_1_on_broken_frontmatter(tmp_path):
    staging, work = make_case(tmp_path, edit=lambda s: s.replace(f"name: {NAME}", "name: Bad_Name"))
    r = _check(staging, work)
    assert r.exit_code == 1
    report = read_model(work / "check-report.json", CheckReport)
    assert not report.passed
    assert [x.ok for x in report.results if x.check == "frontmatter"] == [False]


def test_check_exit_5_on_safety_flag_only(tmp_path):
    staging, work = make_case(
        tmp_path,
        edit=lambda s: s.replace("None mentioned.", "Never run sudo skipdemo unless asked."),
    )
    r = _check(staging, work)
    assert r.exit_code == 5
    report = read_model(work / "check-report.json", CheckReport)
    assert report.passed
    manifest = read_model(staging / "skipwatch.json", Manifest)
    assert [f.kind for f in manifest.safety_flags] == ["sudo"]


def test_check_exit_0_on_good_skill(tmp_path):
    staging, work = make_case(tmp_path)
    r = _check(staging, work)
    assert r.exit_code == 0, r.output


def test_check_writes_valid_report_and_manifest(tmp_path):
    staging, work = make_case(tmp_path)
    r = _check(staging, work, "--json")
    assert r.exit_code == 0
    report = CheckReport.model_validate_json(r.stdout)
    assert report == read_model(work / "check-report.json", CheckReport)
    assert report.skill == NAME and report.passed
    assert [x.check for x in report.results] == list(CHECK_ORDER)
    assert report.counts == Counts(steps=4, on_screen=3, spoken=1)
    manifest = read_model(staging / "skipwatch.json", Manifest)
    assert manifest.name == NAME and manifest.checks_passed
    assert manifest.counts == report.counts and manifest.confidence == "medium"
    assert manifest.files == {}


def test_check_marks_stage_done(tmp_path):
    staging, work = make_case(tmp_path)
    _check(staging, work)
    stages = json.loads((work / "stages.json").read_text(encoding="utf-8"))
    assert stages["stages"]["check"]["status"] == "done"


def test_r_cli_1_check_idempotent(tmp_path):
    staging, work = make_case(tmp_path)
    _check(staging, work)
    first = (work / "check-report.json").read_bytes(), (staging / "skipwatch.json").read_bytes()
    _check(staging, work)
    second = (work / "check-report.json").read_bytes(), (staging / "skipwatch.json").read_bytes()
    assert first == second


def test_r_chk_2_check_redacts_staging(tmp_path):
    staging, work = make_case(tmp_path)
    source = staging / "references" / "source.md"
    source.write_text(source.read_text(encoding="utf-8") + f"\nkey {KEY}\n", encoding="utf-8")
    r = _check(staging, work)
    assert r.exit_code == 0, r.output
    assert KEY not in source.read_text(encoding="utf-8")
    assert KEY not in (work / "check-report.json").read_text(encoding="utf-8")


def test_counts_gaps_and_illegible(tmp_path):
    from skipwatch.checks.runner import counts_for
    from skipwatch.skillmd import parse

    staging, _ = make_case(
        tmp_path,
        edit=lambda s: (
            s.replace(
                "## Unverified and gaps\n\nNone.",
                "## Unverified and gaps\n\n- GAP the video cuts at 00:30.\n- GAP: no output shown.",
            )
            .replace("None shown in the video.", "GAP: unclear branch.")
            .replace("Write a four line poem", "Write a [illegible at 00:25] poem")
        ),
    )
    counts = counts_for(parse((staging / "SKILL.md").read_text(encoding="utf-8")))
    assert counts.gaps == 3 and counts.illegible == 1


def test_check_default_work_is_two_levels_up(tmp_path):
    staging, _ = make_case(tmp_path)
    r = CliRunner().invoke(app, ["check", str(staging)])
    assert r.exit_code == 0, r.output


def test_check_usage_error_without_skill_md(tmp_path):
    staging, work = make_case(tmp_path)
    (staging / "SKILL.md").unlink()
    assert _check(staging, work).exit_code == 64


def test_check_usage_error_without_ingest(tmp_path):
    staging, work = make_case(tmp_path)
    (work / "ingest.json").unlink()
    assert _check(staging, work).exit_code == 64


def test_check_progress_names_each_check(tmp_path):
    staging, work = make_case(tmp_path)
    r = _check(staging, work)
    for name in CHECK_ORDER:
        assert f"{name}:" in r.stderr


# ---- adversarial review (m1d-review) ----


def _bad_input(tmp_path, rel, data: bytes):
    staging, work = make_case(tmp_path)
    (work / rel).parent.mkdir(parents=True, exist_ok=True)
    (work / rel).write_bytes(data)
    return _check(staging, work), work


def test_check_exit_7_on_invalid_critique(tmp_path):
    r, work = _bad_input(tmp_path, "critique.json", b'{"schema":"skipwatch/critique/1","score":99}')
    assert r.exit_code == 7 and "critique.json is not valid" in r.stderr
    stages = json.loads((work / "stages.json").read_text(encoding="utf-8"))
    assert stages["stages"]["check"]["status"] == "failed"


def test_check_exit_7_on_invalid_notes(tmp_path):
    r, _ = _bad_input(tmp_path, "notes/batch-01.json", b"{not json")
    assert r.exit_code == 7 and "batch-01.json is not valid" in r.stderr


def test_check_exit_7_on_non_utf8_notes(tmp_path):
    r, _ = _bad_input(tmp_path, "notes/batch-01.json", b'{"schema": "\xff"}')
    assert r.exit_code == 7 and "batch-01.json is not valid" in r.stderr


def test_check_exit_7_on_invalid_transcript(tmp_path):
    r, _ = _bad_input(tmp_path, "transcript.json", b'{"schema":"skipwatch/transcript/1"}')
    assert r.exit_code == 7 and "transcript.json is not valid" in r.stderr


def test_check_exit_7_on_invalid_ingest(tmp_path):
    r, _ = _bad_input(tmp_path, "ingest.json", b"[]")
    assert r.exit_code == 7 and "ingest.json is not valid" in r.stderr


def test_check_reencodes_non_utf8_skill_md_and_continues(tmp_path):
    staging, work = make_case(tmp_path)
    skill = staging / "SKILL.md"
    skill.write_bytes(skill.read_bytes().replace(b"Sets up a tiny", b"Sets up a \xff tiny"))
    r = _check(staging, work)
    assert r.exit_code == 0, r.output
    skill.read_bytes().decode("utf-8")
    report = read_model(work / "check-report.json", CheckReport)
    redaction = next(x for x in report.results if x.check == "redaction")
    assert "re-encoded SKILL.md" in [i.msg for i in redaction.items]


def test_check_unexpected_error_exits_70_not_1(tmp_path, monkeypatch):
    from skipwatch.checks import style

    def boom(ctx):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(style, "run", boom)
    staging, work = make_case(tmp_path)
    r = _check(staging, work)
    assert r.exit_code == 70
    assert "internal error in skipwatch check: RuntimeError: kaboom" in r.stderr


def test_internal_error_is_an_exit_code():
    from skipwatch.errors import ExitCode

    assert ExitCode.INTERNAL_ERROR == 70


def test_check_fails_on_hardlink_even_when_it_holds_a_key(tmp_path):

    staging, work = make_case(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text(f"outside {KEY}\n", encoding="utf-8")
    hardlink_or_skip(staging / "references" / "hard.md", outside)
    r = _check(staging, work)
    assert r.exit_code == 1
    report = read_model(work / "check-report.json", CheckReport)
    structure = next(x for x in report.results if x.check == "structure")
    assert "hardlink not allowed in a skill: references/hard.md" in [i.msg for i in structure.items]
    assert outside.read_text(encoding="utf-8") == f"outside {KEY}\n"
