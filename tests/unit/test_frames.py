import json
import re
from pathlib import Path

from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.frames import (
    HELD_SECONDS,
    Candidate,
    budget,
    cue_times,
    dedup_runs,
    frame_id,
    sample_cues,
    sample_scene,
    select,
    transcript_window,
)
from skipwatch.media import ffmpeg_paths
from skipwatch.models import FramesFile, IngestBundle, Segment, Transcript, Word
from skipwatch.workdir import WorkDir, read_model, write_model
from tests.unit._media import make_held_video, make_local_work, make_video, needs_ffmpeg


def C(t, reason="scene", h="0" * 16):
    return Candidate(t=t, path=Path(f"/x/{t}.jpg"), reason=reason, dhash=h)


# ---- pure selection logic ----


def test_frame_id_deciseconds():
    assert frame_id(123.0) == "f001230" and frame_id(10.5) == "f000105"


def test_budget_defaults():
    assert budget(642, 3, 60) == 33 and budget(3600, 3, 60) == 60 and budget(5, 3, 60) == 1


def test_dedup_keeps_last_of_run():
    a, b, c = "0" * 16, "0" * 15 + "1", "f" * 16
    kept = dedup_runs([C(1, h=a), C(2, h=b), C(3, h=c)])
    assert [k.t for k in kept] == [2, 3]


def test_cue_frames_survive_dedup():
    kept = dedup_runs([C(1), C(1.5, "cue"), C(2)])
    assert 1.5 in [k.t for k in kept]


def test_dedup_keeps_a_held_frame_inside_a_run():
    # mpdecimate dropped 6..14, so the 5 s frame stayed on screen for 10 s (held text).
    run = [C(float(t)) for t in (0, 1, 2, 3, 4, 5, 15, 16, 17)]
    kept = [k.t for k in dedup_runs(run)]
    assert kept == [5.0, 17.0]


def test_dedup_held_threshold_is_exclusive_below():
    run = [C(0.0), C(HELD_SECONDS - 1), C(HELD_SECONDS)]
    assert [k.t for k in dedup_runs(run)] == [HELD_SECONDS]


def test_r_fr_2_never_exceeds_max_on_90_minutes():
    cands = [C(float(t), h=f"{t:016x}") for t in range(90 * 60)] + [
        C(t + 0.5, "cue") for t in range(0, 5400, 30)
    ]
    n = budget(90 * 60, 3, 60)
    chosen = select(dedup_runs(cands), n)
    assert len(chosen) == n == 60
    thorough = select(dedup_runs(cands), budget(90 * 60, 5, 150))
    assert len(thorough) == 150
    dense = select(dedup_runs(cands), budget(90 * 60, 6, 60))
    assert len(dense) == 60


def test_r_fr_2_cues_alone_never_exceed_max():
    cues = [C(t + 0.5, "cue") for t in range(0, 5400, 5)]  # 1080 cue frames
    chosen = select(cues, 60)
    assert len(chosen) == 60 and all(c.reason == "cue" for c in chosen)
    gaps = [b.t - a.t for a, b in zip(chosen, chosen[1:], strict=False)]
    assert max(gaps) < 2 * 5400 / 60  # an even subset, not the first 60


def test_cues_first_then_spread():
    cands = [C(float(t), h=f"{t:016x}") for t in range(600)] + [C(100.5, "cue"), C(300.5, "cue")]
    chosen = select(cands, 10)
    assert {100.5, 300.5} <= {c.t for c in chosen}
    gaps = [b.t - a.t for a, b in zip(chosen, chosen[1:], strict=False)]
    assert max(gaps) < 200  # spread, not clumped


def test_select_is_sorted_and_unique_and_keeps_all_when_under_budget():
    cands = [C(3.0), C(1.0, "cue"), C(2.0)]
    chosen = select(cands, 10)
    assert [c.t for c in chosen] == [1.0, 2.0, 3.0]
    assert select([], 5) == []


def _transcript(**kw):
    return Transcript(origin="captions", **kw)


def test_cue_times_uses_word_timestamps_whole_word_case_insensitive():
    tr = _transcript(
        segments=[
            Segment(
                start=10.0,
                end=14.0,
                text="Paste this prompt, then typed it",
                words=[
                    Word(w="Paste", s=10.2, e=10.5),
                    Word(w="this", s=10.5, e=10.7),
                    Word(w="prompt,", s=10.7, e=11.2),
                    Word(w="then", s=11.2, e=11.4),
                    Word(w="typed", s=11.4, e=11.8),
                ],
            )
        ]
    )
    assert cue_times(tr, ["paste", "prompt", "type"]) == [10.2, 10.7]


def test_cue_times_falls_back_to_segment_start():
    tr = _transcript(
        segments=[
            Segment(start=4.0, end=6.0, text="now CLICK the button"),
            Segment(start=7.0, end=9.0, text="clicking around"),
            Segment(start=9.0, end=11.0, text="copy and paste"),
        ]
    )
    assert cue_times(tr, ["click", "copy", "paste"]) == [4.0, 9.0]


def test_transcript_window_joins_overlapping_segments():
    tr = _transcript(
        segments=[
            Segment(start=0.0, end=2.0, text="far before"),
            Segment(start=5.0, end=8.0, text="open settings"),
            Segment(start=12.0, end=13.0, text="then run it"),
            Segment(start=30.0, end=31.0, text="far after"),
        ]
    )
    assert transcript_window(tr, 10.0) == "open settings then run it"


# ---- ffmpeg sampling ----


@needs_ffmpeg
def test_r_fr_1_static_text_kept_near_appearance(tmp_path):
    # Review Focus 3: 0-5 s moving pattern, 5-15 s a frozen frame (held text), 15-20 s moving.
    video = make_held_video(tmp_path / "held.mp4")
    ffmpeg, _ = ffmpeg_paths(allow_fetch=False)
    kept = dedup_runs(sample_scene(ffmpeg, video, tmp_path / "out"))
    near = [c for c in kept if 4.5 <= c.t <= 6.5]
    assert near, [c.t for c in kept]
    assert len([c for c in kept if 6.5 < c.t < 15]) == 0  # no duplicate frames during the hold


@needs_ffmpeg
def test_sample_scene_pairs_timestamps_with_files(tmp_path):
    video = make_video(tmp_path / "v.mp4", 6)
    ffmpeg, _ = ffmpeg_paths(allow_fetch=False)
    cands = sample_scene(ffmpeg, video, tmp_path / "out")
    assert [c.t for c in cands] == sorted(c.t for c in cands) and cands[0].t == 0.0
    assert all(c.path.exists() and c.reason == "scene" for c in cands)
    assert all(re.fullmatch(r"[0-9a-f]{16}", c.dhash) for c in cands)


@needs_ffmpeg
def test_sample_cues_two_fps_around_each_cue(tmp_path):
    video = make_video(tmp_path / "v.mp4", 10)
    ffmpeg, _ = ffmpeg_paths(allow_fetch=False)
    cands = sample_cues(ffmpeg, video, tmp_path / "out", [1.0, 6.0], 10.0)
    times = [c.t for c in cands]
    assert times[:6] == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]
    assert 4.0 in times and 7.5 in times and all(c.reason == "cue" for c in cands)
    assert len({frame_id(t) for t in times}) == len(times)  # overlap never repeats an id
    assert all(c.path.exists() for c in cands)


@needs_ffmpeg
def test_sample_scene_handles_paths_with_spaces_and_percent(tmp_path):
    folder = tmp_path / "Screen Recording 100% é"
    folder.mkdir()
    video = make_video(folder / "clip one.mp4", 3)
    ffmpeg, _ = ffmpeg_paths(allow_fetch=False)
    assert sample_scene(ffmpeg, video, folder / "out")


# ---- frames command ----


@needs_ffmpeg
def test_r_cli_1_frames_idempotent(tmp_path, sw_home):
    w = make_local_work(tmp_path, make_video(tmp_path / "v.mp4", 20))
    r1 = CliRunner().invoke(app, ["frames", "--work", str(w)])
    a = (w / "frames.json").read_bytes()
    (w / "frames" / "f999999.jpg").write_bytes(b"stale")
    r2 = CliRunner().invoke(app, ["frames", "--work", str(w)])
    b = (w / "frames.json").read_bytes()
    assert r1.exit_code == r2.exit_code == 0 and a == b
    names = sorted(p.name for p in (w / "frames").iterdir())
    assert names == sorted(f"{f['id']}.jpg" for f in json.loads(a)["frames"])
    assert WorkDir(w).stages().stages["frames"].status == "done"


@needs_ffmpeg
def test_frames_command_cues_windows_and_json(tmp_path, sw_home):
    w = make_local_work(tmp_path, make_video(tmp_path / "v.mp4", 20))
    transcript = Transcript(
        origin="captions",
        segments=[
            Segment(start=8.0, end=10.0, text="now paste the key"),
            Segment(start=15.0, end=16.0, text="done"),
        ],
    )
    write_model(w / "transcript.json", transcript)
    r = CliRunner().invoke(app, ["frames", "--work", str(w), "--json"])
    assert r.exit_code == 0, r.output
    out = FramesFile.model_validate_json(r.stdout)  # R-CLI-2
    assert out == read_model(w / "frames.json", FramesFile)
    cues = [f for f in out.frames if f.reason == "cue"]
    assert cues and all(6.0 <= f.t <= 10.0 for f in cues)
    assert "paste the key" in cues[0].transcript_window
    assert out.sampling.cue_terms and out.sampling.per_minute == 3
    assert len(out.frames) <= 1  # budget(20 s, 3/min) is 1, and a cue frame fills it
    assert all((w / f.path).is_file() for f in out.frames)


@needs_ffmpeg
def test_frames_command_flags_and_silent(tmp_path, sw_home):
    w = make_local_work(tmp_path, make_video(tmp_path / "v.mp4", 30, pattern="testsrc"))
    r = CliRunner().invoke(app, ["frames", "--work", str(w), "--per-minute", "60", "--max", "4"])
    assert r.exit_code == 0, r.output
    out = read_model(w / "frames.json", FramesFile)
    assert out.sampling.per_minute == 60 and out.sampling.max == 4 and len(out.frames) <= 4
    write_model(w / "transcript.json", Transcript(origin="captions", segments=[], silent=True))
    CliRunner().invoke(app, ["frames", "--work", str(w)])
    assert read_model(w / "frames.json", FramesFile).sampling.per_minute == 6
    CliRunner().invoke(app, ["frames", "--work", str(w), "--dense"])
    dense = read_model(w / "frames.json", FramesFile).sampling
    assert dense.dense and dense.per_minute == 6


def test_frames_audio_only_writes_empty_frames(tmp_path, sw_home):
    w = make_local_work(tmp_path, _fake_media(tmp_path))
    bundle = read_model(w / "ingest.json", IngestBundle)
    bundle.source.kind = "audio"
    write_model(w / "ingest.json", bundle)
    r = CliRunner().invoke(app, ["frames", "--work", str(w)])
    assert r.exit_code == 0, r.output
    assert read_model(w / "frames.json", FramesFile).frames == []


def test_frames_without_media_exits_7(tmp_path, sw_home):
    w = make_local_work(tmp_path, _fake_media(tmp_path))
    bundle = read_model(w / "ingest.json", IngestBundle)
    write_model(w / "ingest.json", bundle.model_copy(update={"media": None}))
    r = CliRunner().invoke(app, ["frames", "--work", str(w)])
    assert r.exit_code == 7
    assert WorkDir(w).stages().stages["frames"].status == "failed"


def test_frames_without_ingest_exits_7(tmp_path, sw_home):
    w = tmp_path / "w"
    WorkDir(w).ensure()
    assert CliRunner().invoke(app, ["frames", "--work", str(w)]).exit_code == 7


def test_frames_missing_work_dir_is_a_usage_error(tmp_path, sw_home):
    r = CliRunner().invoke(app, ["frames", "--work", str(tmp_path / "nope")])
    assert r.exit_code == 2 and not (tmp_path / "nope").exists()  # 64 through cli.main


def _fake_media(tmp_path):
    path = tmp_path / "a.m4a"
    path.write_bytes(b"not decoded in these tests")
    return path
