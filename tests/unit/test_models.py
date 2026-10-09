import json

import pytest
from pydantic import ValidationError

from skipwatch.models import (
    SCHEMA_MODELS,
    CheckReport,
    FramesFile,
    IngestBundle,
    Manifest,
    NotesFile,
    Transcript,
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

# IngestContext adds captions_path (M1 localfile), so the dump carries it as null.
INGEST_EXPECTED_DUMP = {
    **INGEST_EXAMPLE,
    "context": {
        "post_text": "full post text",
        "thread": ["c1"],
        "author_replies": ["r"],
        "links": [{"url": "https://github.com/x/y", "title": "README", "text": "t"}],
        "captions_available": False,
        "captions_path": None,
    },
}


def test_ingest_example_from_spec_7_1_round_trips():
    bundle = IngestBundle.model_validate(INGEST_EXAMPLE)
    assert json.loads(bundle.model_dump_json(by_alias=True)) == INGEST_EXPECTED_DUMP


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
    }
    assert set(SCHEMA_MODELS) == expected
