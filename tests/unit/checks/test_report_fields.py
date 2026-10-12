"""Fields check adds to check-report.json for the review screen: the engine's own grade of a
shared pack (pack_confidence) and the ready Provider calls line."""

from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.models import CheckReport, Manifest
from skipwatch.workdir import read_model
from tests.unit.checks.conftest import make_case
from tests.unit.checks.test_pack_mode import ONSCREEN_STEP, WRITTEN_STEP, _skill, pack_ctx

GAPS = "- GAP: the video cuts at 00:30.\n- GAP: no output shown."


def _report(staging, work) -> CheckReport:
    CliRunner().invoke(app, ["check", str(staging), "--work", str(work)])
    return read_model(work / "check-report.json", CheckReport)


def test_pack_mode_report_carries_the_engine_grade_without_a_critic(tmp_path):
    staging, work = pack_ctx(tmp_path, _skill(f"{ONSCREEN_STEP}\n\n{WRITTEN_STEP}"))
    report = _report(staging, work)
    assert report.counts.steps == 2 and report.counts.gaps == 0
    # the pack claims high with critic 8.5; the engine never grades a pack high
    assert report.pack_confidence == "medium"
    assert read_model(staging / "skipwatch.json", Manifest).confidence == "high"


def test_pack_mode_grade_is_low_with_two_gaps(tmp_path):
    staging, work = pack_ctx(tmp_path, _skill(f"{ONSCREEN_STEP}\n\n{WRITTEN_STEP}", gaps=GAPS))
    report = _report(staging, work)
    assert report.counts.gaps == 2
    assert report.pack_confidence == "low"


def test_run_mode_report_has_no_pack_confidence(tmp_path):
    staging, work = make_case(tmp_path)
    report = _report(staging, work)
    assert report.pack_confidence is None
