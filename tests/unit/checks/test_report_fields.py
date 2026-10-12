"""Fields check adds to check-report.json for the review screen: the engine's own grade of a
shared pack (pack_confidence) and the ready Provider calls line."""

import json

from typer.testing import CliRunner

from skipwatch.calls_line import provider_calls_line
from skipwatch.cli import app
from skipwatch.models import (
    CallsFile,
    CheckReport,
    IngestBundle,
    Manifest,
    ProviderCall,
    Route,
    SourceInfo,
)
from skipwatch.workdir import read_model, write_model
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


# ---- Provider calls line (skill audit 2 fix 17; review-screen.md "Provider calls") ----


def _call(op: str, cost: float, provider: str = "treg", error: str | None = None) -> ProviderCall:
    return ProviderCall(provider=provider, op=op, ok=error is None, cost_usd=cost, error=error)


M4_CALLS = [_call("x.thread", 0.0038), _call("x.comments", 0.01), _call("x.transcript", 0.0012)]
M4_LINE = "treg: 3 calls, $0.0150 (x.thread $0.0038, x.comments $0.0100, x.transcript $0.0012)"


def _ingest(**update) -> IngestBundle:
    bundle = IngestBundle(
        source=SourceInfo(kind="video", platform="x", url="https://x.com/a/status/1"),
        route=Route(context="treg"),
    )
    return bundle.model_copy(update=update)


def test_calls_line_m4_example():
    assert provider_calls_line(M4_CALLS, _ingest(), 0.05) == M4_LINE


def test_calls_line_no_rows_is_the_free_route():
    assert provider_calls_line([], _ingest(), 0.05) == "none (free route)"


def test_calls_line_counts_only_treg_rows():
    calls = [_call("link.get", 0.5, provider="links"), *M4_CALLS, _call("op", 1, "other")]
    assert provider_calls_line(calls, _ingest(), 0.05) == M4_LINE
    only_others = [_call("link.get", 0.5, provider="links")]
    assert provider_calls_line(only_others, _ingest(), 0.05) == "none (free route)"


def test_calls_line_media_get_shows_zero_and_adds_nothing():
    calls = [_call("x.thread", 0.0038), _call("media.get", 0.02)]
    assert provider_calls_line(calls, _ingest(), 0.05) == (
        "treg: 2 calls, $0.0038 (x.thread $0.0038, media.get $0.0000)"
    )


def test_calls_line_cost_cap_rows_are_refused_and_add_nothing():
    calls = [_call("x.thread", 0.0038), _call("x.comments", 0.01, error="cost cap")]
    assert provider_calls_line(calls, _ingest(), 0.05) == (
        "treg: 2 calls, $0.0038 (x.thread $0.0038, x.comments refused (cost cap))"
    )


def test_calls_line_cost_cap_reached_suffix_names_the_cap():
    capped = _ingest(route=Route(context="treg", fallbacks=["treg: cost cap reached"]))
    calls = [_call("x.thread", 0.0038), _call("x.comments", 0.01, error="cost cap")]
    line = provider_calls_line(calls, capped, 0.05)
    assert line.endswith("x.comments refused (cost cap)); treg cost cap reached ($0.05)")
    assert provider_calls_line(calls, capped, 0.125).endswith("($0.125)")
    assert provider_calls_line(calls, _ingest(), 0.05).endswith("(cost cap))")


def test_calls_line_cache_suffix_uses_the_cache_date():
    hit = _ingest(from_cache=True, cached_at="2026-10-09T12:00:00Z")
    assert provider_calls_line([], hit, 0.05) == "none (free route); cached from 2026-10-09"
    old = _ingest(from_cache=True)
    assert provider_calls_line(M4_CALLS, old, 0.05) == M4_LINE + "; cached from an earlier run"


def test_calls_line_cap_suffix_comes_before_the_cache_suffix():
    both = _ingest(
        route=Route(context="treg", fallbacks=["treg: cost cap reached"]),
        from_cache=True,
        cached_at="2026-10-09T12:00:00Z",
    )
    assert provider_calls_line([], both, 0.05) == (
        "none (free route); treg cost cap reached ($0.05); cached from 2026-10-09"
    )


def test_check_writes_the_calls_line_from_calls_json_and_config(tmp_path, sw_home):
    staging, work = make_case(tmp_path)
    write_model(work / "calls.json", CallsFile(calls=M4_CALLS))
    raw = json.loads((work / "ingest.json").read_text(encoding="utf-8"))
    raw["route"]["fallbacks"] = ["treg: cost cap reached"]
    (work / "ingest.json").write_text(json.dumps(raw), encoding="utf-8")
    sw_home.mkdir(parents=True, exist_ok=True)
    (sw_home / "config.toml").write_text("[providers.treg]\nmax_cost_usd = 0.02\n")
    report = _report(staging, work)
    assert report.provider_calls_line == M4_LINE + "; treg cost cap reached ($0.02)"


def test_check_without_calls_json_is_the_free_route(tmp_path):
    staging, work = make_case(tmp_path)
    assert _report(staging, work).provider_calls_line == "none (free route)"


def test_check_in_a_pack_folder_is_the_shared_pack(tmp_path):
    staging, work = pack_ctx(tmp_path, _skill(f"{ONSCREEN_STEP}\n\n{WRITTEN_STEP}"))
    write_model(work / "calls.json", CallsFile(calls=M4_CALLS))
    assert _report(staging, work).provider_calls_line == "none (shared pack)"
