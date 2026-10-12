import json

import pytest
from pydantic import ValidationError

from skipwatch.models import (
    SCHEMA_MODELS,
    CacheEntry,
    CheckReport,
    Config,
    Counts,
    ExportLog,
    ExportLogEntry,
    FramesFile,
    IngestBundle,
    InstallRecord,
    InstallsFile,
    ListedSkill,
    ListResult,
    Manifest,
    ManifestSource,
    NotesFile,
    PackOrigin,
    PackResult,
    ProbeResult,
    ProviderCall,
    ResumeResult,
    Route,
    RunFile,
    Segment,
    ShareResult,
    SourceInfo,
    TesterReport,
    Transcript,
    UnpackResult,
)

INGEST_EXAMPLE = {
    "schema": "skipwatch/ingest/1",
    "source": {
        "kind": "video",
        "platform": "x",
        "url": "https://x.com/creator/status/123",
        "canonical_url": "https://x.com/i/status/123",
        "path": None,
        "author": "@creator",
        "author_name": "Creator Name",
        "title": "How I loop motion graphics in 3 steps",
        "posted_at": "2026-09-30T14:02:00Z",
        "duration_s": 642.0,
    },
    "context": {
        "post_text": "full post text",
        "thread": ["c1"],
        "author_replies": ["r"],
        "links": [{"url": "https://github.com/x/y", "title": "README", "text": "t"}],
        "captions_available": False,
    },
    "media": {
        "path": "media/video.mp4",
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "has_audio": True,
    },
    "transcript_hint": {"origin": "none", "text": None},
    "provider_calls": [
        {"provider": "free", "op": "yt-dlp.metadata", "ok": True, "cost_usd": 0, "ms": 2100}
    ],
    "route": {"context": "free", "media": "free", "fallbacks": []},
    "fetched_with_cookies": False,
}

# Fields added after the spec example: captions_path (M1 localfile), captions_lang,
# captions_kind, from_cache and the provider call review fields (M2-A). The dump carries
# them with their defaults.
ADDED_CONTEXT_DEFAULTS = {"captions_path": None, "captions_lang": None, "captions_kind": None}
ADDED_TOP_DEFAULTS = {"from_cache": False, "pack": None}
ADDED_CALL_DEFAULTS = {"endpoint": None, "call_id": None, "review": None, "error": None}


def test_ingest_example_from_spec_7_1_round_trips():
    bundle = IngestBundle.model_validate(INGEST_EXAMPLE)
    dumped = json.loads(bundle.model_dump_json(by_alias=True, exclude_defaults=False))
    added_context = {k: dumped["context"].pop(k) for k in ADDED_CONTEXT_DEFAULTS}
    added_top = {k: dumped.pop(k) for k in ADDED_TOP_DEFAULTS}
    for call in dumped["provider_calls"]:
        assert {k: call.pop(k) for k in ADDED_CALL_DEFAULTS} == ADDED_CALL_DEFAULTS
    assert added_context == ADDED_CONTEXT_DEFAULTS
    assert added_top == ADDED_TOP_DEFAULTS
    assert {k: dumped[k] for k in INGEST_EXAMPLE} == INGEST_EXAMPLE
    assert set(dumped) == set(INGEST_EXAMPLE)


def test_ingest_rejects_wrong_schema_tag():
    bad = dict(INGEST_EXAMPLE, schema="skipwatch/ingest/2")
    with pytest.raises(ValidationError):
        IngestBundle.model_validate(bad)


def test_r_tr_1_segments_require_timings():
    with pytest.raises(ValidationError):
        Transcript.model_validate(
            {
                "schema": "skipwatch/transcript/1",
                "origin": "captions",
                "segments": [{"text": "no timings"}],
            }
        )


def test_r_tr_1_words_optional():
    t = Transcript.model_validate(
        {
            "schema": "skipwatch/transcript/1",
            "origin": "captions",
            "segments": [{"start": 1.0, "end": 2.0, "text": "hi"}],
        }
    )
    assert t.segments[0].words is None and t.silent is False


def test_frames_reason_is_enumerated():
    with pytest.raises(ValidationError):
        FramesFile.model_validate(
            {
                "schema": "skipwatch/frames/1",
                "sampling": {"per_minute": 3, "max": 60, "dense": False, "cue_terms": []},
                "frames": [
                    {
                        "id": "f000010",
                        "t": 1.0,
                        "path": "frames/f000010.jpg",
                        "reason": "random",
                        "transcript_window": "",
                        "dhash": "0" * 16,
                    }
                ],
            }
        )


def test_r_notes_1_verbatim_confidence_bounded():
    with pytest.raises(ValidationError):
        NotesFile.model_validate(
            {
                "schema": "skipwatch/notes/1",
                "batch": 1,
                "frames": [
                    {
                        "id": "f000010",
                        "t": 1.0,
                        "shows": "terminal",
                        "verbatim": [{"kind": "command", "text": "ls", "confidence": 1.5}],
                        "illegible": [],
                        "new_since_previous": True,
                        "note": "x",
                    }
                ],
            }
        )


def test_check_report_example_from_spec_7_5():
    CheckReport.model_validate(
        {
            "schema": "skipwatch/check/1",
            "skill": "a-b",
            "passed": False,
            "results": [
                {
                    "check": "safety",
                    "ok": True,
                    "flags": [
                        {
                            "step": 7,
                            "kind": "pipe_to_shell",
                            "text": "curl ... | sh",
                            "severity": "high",
                        }
                    ],
                }
            ],
            "counts": {
                "steps": 12,
                "spoken": 7,
                "on_screen": 3,
                "written": 0,
                "inferred": 2,
                "gaps": 0,
                "illegible": 1,
            },
        }
    )


def test_manifest_confidence_enumerated():
    with pytest.raises(ValidationError):
        Manifest.model_validate(
            {
                "schema": "skipwatch/manifest/1",
                "name": "run-skipdemo-tutorial",
                "description": "Run the skipdemo tutorial. Use when asked to run skipdemo.",
                "skipwatch_version": "0.1.0",
                "source": {
                    "url": None,
                    "canonical_url": None,
                    "platform": "local",
                    "author": None,
                    "title": "t",
                    "posted_at": None,
                },
                "extracted_at": "2026-10-09T18:20:00Z",
                "fetched_with_cookies": False,
                "counts": {
                    "steps": 1,
                    "spoken": 1,
                    "on_screen": 0,
                    "written": 0,
                    "inferred": 0,
                    "gaps": 0,
                },
                "confidence": "great",
                "critic_score": None,
                "checks_passed": True,
                "safety_flags": [],
                "files": {},
            }
        )


def test_r_arch_2_registry_covers_every_work_file():
    expected = {
        "ingest",
        "transcript",
        "frames",
        "batches",
        "notes",
        "check",
        "manifest",
        "stages",
        "source",
        "calls",
        "critique",
        "doctor",
        "cache",
        "install",
        "config",
        "probe",
        "run",
        "resume",
        "cache-entry",
        "installs",
        "export-log",
        "test-report",
        "pack",
        "unpack",
        "list",
        "share",
    }
    assert set(SCHEMA_MODELS) == expected


TAGGED = {key: model for key, model in SCHEMA_MODELS.items() if key != "config"}


@pytest.mark.parametrize("key", sorted(TAGGED))
def test_schema_tag_required_when_reading(key):
    model = TAGGED[key]
    with pytest.raises(ValidationError, match="schema"):
        model.model_validate({})
    with pytest.raises(ValidationError, match="schema"):
        model.model_validate_json("{}")


@pytest.mark.parametrize("key", sorted(TAGGED))
def test_schema_tag_required_in_json_schema(key):
    assert "schema" in TAGGED[key].model_json_schema(by_alias=True).get("required", [])


def test_schema_tag_filled_on_construction():
    t = Transcript(origin="captions", segments=[])
    assert t.schema_ == "skipwatch/transcript/1"
    assert json.loads(t.model_dump_json(by_alias=True))["schema"] == "skipwatch/transcript/1"
    assert Transcript.model_validate_json(t.model_dump_json(by_alias=True)) == t


def test_ingest_missing_schema_tag_rejected():
    data = {k: v for k, v in INGEST_EXAMPLE.items() if k != "schema"}
    with pytest.raises(ValidationError):
        IngestBundle.model_validate(data)


MANIFEST_EXAMPLE = {
    "schema": "skipwatch/manifest/1",
    "name": "run-skipdemo-tutorial",
    "description": "Run the skipdemo tutorial. Use when asked to run skipdemo.",
    "skipwatch_version": "0.1.0",
    "source": {"platform": "local", "title": "t"},
    "extracted_at": "2026-10-09T18:20:00Z",
    "counts": {"steps": 1, "spoken": 1},
    "confidence": "medium",
    "checks_passed": True,
}


def test_manifest_carries_name_and_description_for_list():
    m = Manifest.model_validate(MANIFEST_EXAMPLE)
    assert (m.name, m.description) == (MANIFEST_EXAMPLE["name"], MANIFEST_EXAMPLE["description"])


@pytest.mark.parametrize("field", ["name", "description"])
def test_manifest_name_and_description_required(field):
    data = {k: v for k, v in MANIFEST_EXAMPLE.items() if k != field}
    with pytest.raises(ValidationError):
        Manifest.model_validate(data)


def test_provider_call_carries_review_fields():
    c = ProviderCall(
        provider="treg",
        op="x.thread",
        ok=True,
        cost_usd=0.00375,
        ms=900,
        endpoint="anyapi.twitter.thread",
        call_id="abc",
        review="useful",
    )
    assert c.review == "useful"
    with pytest.raises(ValidationError):
        ProviderCall(provider="treg", op="x", ok=True, review="great")  # pyright: ignore[reportArgumentType]


def test_ingest_example_still_round_trips_with_new_defaults():
    bundle = IngestBundle.model_validate(INGEST_EXAMPLE)
    assert bundle.from_cache is False and bundle.context.captions_kind is None
    assert bundle.context.captions_lang is None


def test_ingest_context_captions_kind_enumerated():
    data = dict(INGEST_EXAMPLE, context={"captions_kind": "machine"})
    with pytest.raises(ValidationError):
        IngestBundle.model_validate(data)


def test_treg_cost_cap_default_and_bounds():
    assert Config().providers.treg.max_cost_usd == 0.05
    with pytest.raises(ValidationError):
        Config.model_validate({"providers": {"treg": {"max_cost_usd": -1.0}}})


def test_probe_and_resume_require_schema_tag_on_read():
    with pytest.raises(ValidationError):
        ProbeResult.model_validate({"value": "u", "kind": "video", "platform": "youtube"})
    r = ResumeResult(
        work="/w",
        next_stage="frames",
        completed=["detect", "ingest", "transcribe"],
        run=RunFile(
            input="https://youtu.be/x", flags=["--thorough"], started_at="2026-10-09T18:00:00Z"
        ),
    )
    assert ResumeResult.model_validate_json(r.model_dump_json(by_alias=True)) == r


def test_probe_result_defaults_and_kind():
    p = ProbeResult(value="https://youtu.be/x", kind="video", platform="youtube")
    assert (p.captions_available, p.long_video, p.duration_s) == (False, False, None)
    assert ProbeResult.model_validate_json(p.model_dump_json(by_alias=True)) == p
    with pytest.raises(ValidationError):
        ProbeResult(value="u", kind="podcast", platform="x")  # pyright: ignore[reportArgumentType]


def test_resume_next_stage_may_be_none_but_is_required():
    r = ResumeResult(work="/w", next_stage=None)
    assert r.completed == [] and r.run is None and r.media_present is False
    with pytest.raises(ValidationError):
        ResumeResult.model_validate({"schema": "skipwatch/resume/1", "work": "/w"})


def test_cache_entry_round_trip():
    e = CacheEntry(
        key="0123456789abcdef",
        source="https://youtu.be/x",
        created_at="2026-10-09T18:00:00Z",
        files=["ingest.json"],
    )
    assert CacheEntry.model_validate_json(e.model_dump_json(by_alias=True)) == e


# ---- M5-A: model amendments for M5 and M6 ----


def test_transcript_origin_accepts_pack():
    t = Transcript(origin="pack", segments=[Segment(start=1.0, end=2.0, text="hi there you")])
    assert t.origin == "pack"
    assert Transcript.model_validate_json(t.model_dump_json(by_alias=True)) == t


def test_mem0_user_id_default_empty():
    assert Config().exports.mem0.user_id == "" and Config().exports.mem0.enabled is False
    cfg = Config.model_validate({"exports": {"mem0": {"user_id": "someone"}}})
    assert cfg.exports.mem0.user_id == "someone"


def _manifest() -> Manifest:
    return Manifest(
        name="run-x",
        description="d",
        skipwatch_version="0.1.0",
        source=ManifestSource(platform="youtube", url="https://youtu.be/x"),
        extracted_at="2026-10-09T18:20:00Z",
        counts=Counts(steps=4),
        confidence="high",
        critic_score=8.5,
        checks_passed=True,
        files={"SKILL.md": "sha256:" + "0" * 64},
    )


def test_ingest_carries_pack_origin_round_trip():
    bundle = IngestBundle.model_validate(
        {
            "schema": "skipwatch/ingest/1",
            "source": {"kind": "video", "platform": "youtube"},
            "route": {"context": "pack"},
            "pack": {
                "file": "a.skillpack.zip",
                "sha256": "sha256:" + "1" * 64,
                "manifest": _manifest().model_dump(by_alias=True),
            },
        }
    )
    assert bundle.pack is not None and bundle.pack.manifest.confidence == "high"
    assert bundle.pack.manifest == _manifest()
    assert IngestBundle.model_validate_json(bundle.model_dump_json(by_alias=True)) == bundle


def test_run_ingest_has_no_pack_by_default():
    bundle = IngestBundle(
        source=SourceInfo(kind="file", platform="local"), route=Route(context="local")
    )
    assert bundle.pack is None


def test_pack_origin_manifest_needs_its_schema_tag():
    raw = _manifest().model_dump(by_alias=True)
    del raw["schema"]
    with pytest.raises(ValidationError):
        PackOrigin.model_validate({"file": "a", "sha256": "sha256:" + "1" * 64, "manifest": raw})


def test_installs_file_round_trip_and_scope():
    rec = InstallRecord(
        name="run-x", path="/s/run-x", scope="dir", installed_at="2026-10-09T18:20:00Z"
    )
    assert rec.origin == "run"
    f = InstallsFile(installs=[rec, rec.model_copy(update={"origin": "pack"})])
    assert InstallsFile.model_validate_json(f.model_dump_json(by_alias=True)) == f
    assert InstallsFile().installs == []
    with pytest.raises(ValidationError):
        InstallRecord.model_validate({**rec.model_dump(), "scope": "global"})
    with pytest.raises(ValidationError):
        InstallRecord.model_validate({**rec.model_dump(), "origin": "url"})


def test_export_log_round_trip():
    entry = ExportLogEntry(
        provider="mem0",
        name="run-x",
        manifest_sha256="sha256:" + "2" * 64,
        exported_at="2026-10-09T18:20:00Z",
    )
    assert entry.ref is None
    log = ExportLog(entries=[entry])
    assert ExportLog.model_validate_json(log.model_dump_json(by_alias=True)) == log
    assert ExportLog().entries == []
    with pytest.raises(ValidationError):
        ExportLogEntry.model_validate({"provider": "mem0", "name": "run-x"})


def test_tester_report_blocked_needs_step_and_detail():
    assert TesterReport(outcome="completed", task="do it").step is None
    with pytest.raises(ValidationError):
        TesterReport(outcome="blocked", task="do it")
    with pytest.raises(ValidationError):
        TesterReport(outcome="blocked", detail="needs an account", task="do it")
    with pytest.raises(ValidationError):
        TesterReport(outcome="ambiguous", step=2, detail="", task="do it")
    assert TesterReport(outcome="blocked", step=3, detail="needs an account", task="t").step == 3
    with pytest.raises(ValidationError):
        TesterReport(outcome="blocked", step=0, detail="x", task="t")
    with pytest.raises(ValidationError):
        TesterReport(outcome="ambiguous", step=1, detail="x" * 501, task="t")
    r = TesterReport(outcome="ambiguous", step=1, detail="which folder?", task="t")
    assert TesterReport.model_validate_json(r.model_dump_json(by_alias=True)) == r


def test_tester_report_is_not_collected_by_pytest():
    # pytest collects every Test* class it can see, so the rename alone (issue 25) is not enough
    assert getattr(TesterReport, "__test__", True) is False


def test_pack_result_round_trip():
    r = PackResult(
        name="run-x", path="/p/run-x.skillpack.zip", sha256="sha256:" + "3" * 64, files=3, bytes=9
    )
    assert r.ignored == []
    assert PackResult.model_validate_json(r.model_dump_json(by_alias=True)) == r
    with pytest.raises(ValidationError):
        PackResult.model_validate({"name": "run-x"})


def test_unpack_result_round_trip_and_claims():
    r = UnpackResult(
        name="run-x",
        work="/h/packs/run-x-20261009-182000",
        staging="/h/packs/run-x-20261009-182000/staging/run-x",
        pack_sha256="sha256:" + "4" * 64,
        files=3,
        claimed_confidence="high",
        transcript=True,
    )
    assert r.fetched_from is None and r.claimed_critic_score is None
    assert UnpackResult.model_validate_json(r.model_dump_json(by_alias=True)) == r
    with pytest.raises(ValidationError):
        UnpackResult.model_validate({"name": "x"})
    with pytest.raises(ValidationError):
        UnpackResult.model_validate(
            {**r.model_dump(by_alias=True), "claimed_confidence": "certain"}
        )


def test_list_result_round_trip_and_problem_entries():
    ok = ListedSkill(
        name="run-x", path="/s/run-x", scope="user", confidence="medium", critic_score=7.5
    )
    bad = ListedSkill(name="broken", path="/s/broken", scope="dir", problem="unreadable")
    assert ok.origin == "unknown" and ok.problem is None and bad.confidence is None
    r = ListResult(skills=[bad, ok])
    assert ListResult.model_validate_json(r.model_dump_json(by_alias=True)) == r
    assert ListResult().skills == []
    with pytest.raises(ValidationError):
        ListedSkill.model_validate({**ok.model_dump(), "origin": "url"})


def test_share_result_round_trip():
    r = ShareResult(
        name="run-x", text="Thanks", weighted_length=6, install_line="/skipwatch https://youtu.be/x"
    )
    assert ShareResult.model_validate_json(r.model_dump_json(by_alias=True)) == r
    with pytest.raises(ValidationError):
        ShareResult.model_validate({"schema": "skipwatch/share/1", "name": "run-x"})
