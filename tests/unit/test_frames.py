import json
import math
import re
import subprocess
from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.frames import (
    DUP_FRACTION,
    HELD_SECONDS,
    Candidate,
    budget,
    changed_fraction,
    cue_times,
    dedup_runs,
    frame_id,
    sample_cues,
    sample_scene,
    select,
    thumbnail,
    transcript_window,
)
from skipwatch.media import ffmpeg_paths
from skipwatch.models import FramesFile, IngestBundle, MediaInfo, Segment, Transcript, Word
from skipwatch.workdir import WorkDir, read_model, write_model
from tests.unit._media import (
    editor_frame,
    make_blinking_cursor_video,
    make_held_video,
    make_local_work,
    make_typed_code_video,
    make_video,
    needs_ffmpeg,
)


def C(t, reason="scene", level=0):
    """A candidate whose thumbnail is a flat gray `level`: equal levels are duplicates."""
    thumb = Image.new("L", (32, 18), level)
    return Candidate(t=t, path=Path(f"/x/{t}.jpg"), reason=reason, dhash="0" * 16, thumb=thumb)


# ---- pure selection logic ----


def test_frame_id_deciseconds():
    assert frame_id(123.0) == "f001230" and frame_id(10.5) == "f000105"


def test_budget_defaults():
    assert budget(642, 3, 60) == 33 and budget(3600, 3, 60) == 60 and budget(5, 3, 60) == 1


def test_dedup_keeps_last_of_run():
    kept = dedup_runs([C(1, level=0), C(2, level=10), C(3, level=255)])
    assert [k.t for k in kept] == [2, 3]


def test_cue_frames_survive_dedup():
    kept = dedup_runs([C(1), C(1.5, "cue"), C(2)])
    assert 1.5 in [k.t for k in kept]


def test_dedup_long_run_keeps_its_first_and_last_frame():
    # One run of duplicates lasting 17 s: its first frame is the appearance (Review Focus 3).
    run = [C(float(t)) for t in (0, 1, 2, 3, 4, 5, 15, 16, 17)]
    assert [k.t for k in dedup_runs(run)] == [0.0, 17.0]


def test_dedup_held_threshold_is_run_duration():
    assert [k.t for k in dedup_runs([C(0.0), C(HELD_SECONDS - 1)])] == [HELD_SECONDS - 1]
    assert [k.t for k in dedup_runs([C(0.0), C(HELD_SECONDS)])] == [0.0, HELD_SECONDS]


def test_dedup_blinking_cursor_runs_keep_appearance():
    # Every 1 s frame survives mpdecimate (cursor blink), so no gap reaches HELD_SECONDS.
    levels = [0, 0] + [100] * 10 + [200] * 8
    kept = [k.t for k in dedup_runs([C(float(t), level=v) for t, v in enumerate(levels)])]
    assert kept == [1.0, 2.0, 11.0, 12.0, 19.0]


def test_r_fr_2_never_exceeds_max_on_90_minutes():
    cands = [C(float(t), level=(t % 2) * 255) for t in range(90 * 60)] + [
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
    cands = [C(float(t), level=(t % 2) * 255) for t in range(600)]
    cands += [C(100.5, "cue"), C(300.5, "cue")]
    chosen = select(cands, 10)
    assert {100.5, 300.5} <= {c.t for c in chosen}
    gaps = [b.t - a.t for a, b in zip(chosen, chosen[1:], strict=False)]
    assert max(gaps) < 200  # spread, not clumped


def test_cue_frames_bypass_the_per_minute_budget():
    # 60 s at 3 per minute is a budget of 3, but every cue frame is kept (spec 3.4).
    scenes = [C(float(t), level=(t % 2) * 255) for t in range(60)]
    cues = [C(t + 0.5, "cue") for t in (9, 10, 24, 25, 39, 40)]
    chosen = select(scenes + cues, 3, max_frames=60)
    assert {c.t for c in cues} <= {c.t for c in chosen}
    assert [c.reason for c in chosen].count("scene") == 1  # the floor: ceil(3 / 3)
    two = select(scenes + cues[:2], 3, max_frames=60)
    assert [c.reason for c in two].count("cue") == 2 and len(two) == 3


def test_scene_floor_keeps_scenes_when_cues_are_common():
    scenes = [C(float(t), level=(t % 2) * 255) for t in range(600)]  # 10 minutes
    cues = [C(t * 15 + 0.5, "cue") for t in range(40)]
    n = budget(600, 3, 60)
    chosen = select(scenes + cues, n, max_frames=60)
    reasons = [c.reason for c in chosen]
    # 40 cues exceed half of max, so they are cut to 30; scenes keep the floor of 10
    assert (reasons.count("cue"), reasons.count("scene")) == (30, 10)


def test_scene_floor_when_cues_exceed_max():
    scenes = [C(float(t), level=(t % 2) * 255) for t in range(600)]
    cues = [C(t * 5 + 0.5, "cue") for t in range(100)]
    chosen = select(scenes + cues, 30, max_frames=60)
    reasons = [c.reason for c in chosen]
    assert (reasons.count("cue"), reasons.count("scene")) == (30, 10)


G5_DURATION = 2183.0  # golden G5: a 36-minute slide talk where cue words are common speech


def g5_like_candidates():
    """Slides change every 25 s; cue frames are sparse early and dense in minutes 10 to 25."""
    scenes = [C(float(t), level=(i % 2) * 255) for i, t in enumerate(range(0, 2183, 25))]
    cue_times = [40.0, 220.0] + [300.0 + 30 * i for i in range(10)]
    cue_times += [600.0 + 6 * i for i in range(150)] + [1500.0 + 45 * i for i in range(15)]
    return scenes + [C(t + 0.5, "cue") for t in cue_times]


def per_window(chosen, width=300.0, duration=G5_DURATION):
    counts = [0] * math.ceil(duration / width)
    for c in chosen:
        counts[int(c.t // width)] += 1
    return counts


def test_g5_like_talk_covers_every_five_minutes_and_caps_cue_share():
    n = budget(G5_DURATION, 3, 60)
    chosen = select(dedup_runs(g5_like_candidates()), n, max_frames=60, duration=G5_DURATION)
    counts = per_window(chosen)
    assert len(chosen) <= 60
    assert min(counts) >= 2 and min(counts[:-1]) >= 4, counts  # the last window is 83 s
    cues = [c for c in chosen if c.reason == "cue"]
    assert len(cues) <= len(chosen) / 2, (len(cues), len(chosen))


def test_coverage_window_without_scenes_keeps_a_cue():
    # Minutes 4 to 6 hold no scene frame and one lone cue among 200 dense ones.
    ts = list(range(0, 200)) + list(range(400, 600))
    scenes = [C(float(t), level=(t % 2) * 255) for t in ts]
    cues = [C(t + 0.5, "cue") for t in range(0, 200, 2)] + [C(300.5, "cue")]
    cues += [C(t + 0.5, "cue") for t in range(400, 600, 2)]
    chosen = select(scenes + cues, 10, max_frames=10, duration=600.0)
    assert any(c.t == 300.5 for c in chosen), [c.t for c in chosen]
    assert len(chosen) <= 10


def test_cue_share_cap_prefers_the_cue_that_shows_something_new():
    scenes = [C(float(t), level=100) for t in (1, 30, 80, 95)]
    cues = [C(10.5, "cue", level=0), C(60.5, "cue", level=0), C(70.5, "cue", level=255)]
    chosen = select(scenes + cues, 4, max_frames=4, duration=100.0)
    assert [c.t for c in chosen if c.reason == "cue"] == [10.5, 70.5]


def test_cue_frames_are_capped_by_max_only():
    cues = [C(t + 0.5, "cue") for t in range(100)]
    assert len(select(cues, 3, max_frames=60)) == 60


def test_changed_fraction_sees_a_new_line_but_not_typing():
    base = thumbnail(editor_frame(3))
    assert changed_fraction(base, thumbnail(editor_frame(3))) == 0
    typing = changed_fraction(thumbnail(editor_frame(3, extra_chars=2)), base)
    new_line = changed_fraction(thumbnail(editor_frame(4)), base)
    assert typing < DUP_FRACTION < new_line, (typing, new_line)


def test_dedup_collapses_partial_typing_and_keeps_each_line(tmp_path):
    states = [(1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (3, 0)]  # (full lines, typed chars)
    cands = []
    for i, (lines, extra) in enumerate(states):
        path = tmp_path / f"s{i}.jpg"
        editor_frame(lines, extra).save(path, quality=90)
        cands.append(Candidate(t=float(i), path=path, reason="scene", dhash="0" * 16))
    assert [c.t for c in dedup_runs(cands)] == [2.0, 4.0, 5.0]


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
def test_sample_cues_keeps_changes_in_the_window(tmp_path):
    video = make_video(tmp_path / "v.mp4", 10)  # testsrc2 moves, so every frame is a change
    ffmpeg, _ = ffmpeg_paths(allow_fetch=False)
    cands = sample_cues(ffmpeg, video, tmp_path / "out", [1.0, 6.0], 10.0)
    times = [c.t for c in cands]
    assert times == sorted(times) and 0.5 in times and 8.5 in times
    assert all(c.reason == "cue" and c.path.exists() for c in cands)
    assert len({frame_id(t) for t in times}) == len(times)  # overlap never repeats an id


@needs_ffmpeg
def test_sample_cues_still_window_keeps_the_frame_nearest_the_cue(tmp_path):
    video = make_held_video(tmp_path / "held.mp4")  # still from 5 s to 15 s
    ffmpeg, _ = ffmpeg_paths(allow_fetch=False)
    cands = sample_cues(ffmpeg, video, tmp_path / "out", [9.0], 20.0)
    assert [c.t for c in cands] == [9.0]


@needs_ffmpeg
def test_cue_frame_lands_after_text_appears(tmp_path):
    # Line 4 appears at 6 s; the cue word is spoken 1 s earlier, as in the fixture.
    video = make_typed_code_video(tmp_path / "code.mp4")
    ffmpeg, _ = ffmpeg_paths(allow_fetch=False)
    cands = sample_cues(ffmpeg, video, tmp_path / "out", [5.0], 20.0)
    assert any(6.0 <= c.t < 7.0 for c in cands), [c.t for c in cands]
    assert len(cands) <= 3, [c.t for c in cands]  # one per on-screen change, not 2 per second


def test_cursor_blink_is_under_the_duplicate_threshold():
    on, off = thumbnail(editor_frame(1, cursor=True)), thumbnail(editor_frame(1))
    assert 0 < changed_fraction(on, off) < DUP_FRACTION


@needs_ffmpeg
def test_blinking_cursor_keeps_each_line_near_its_appearance(tmp_path):
    video = make_blinking_cursor_video(tmp_path / "blink.mp4")
    ffmpeg, _ = ffmpeg_paths(allow_fetch=False)
    sampled = sample_scene(ffmpeg, video, tmp_path / "out")
    assert len(sampled) >= 18  # the blink defeats mpdecimate, as in the reviewer's case
    kept = [c.t for c in dedup_runs(sampled)]
    assert {2.0, 11.0, 12.0, 19.0} <= set(kept), kept
    assert not [t for t in kept if 3.0 <= t <= 10.0], kept


@needs_ffmpeg
def test_typed_code_keeps_every_line_state(tmp_path):
    video = make_typed_code_video(tmp_path / "code.mp4", lines=10)
    ffmpeg, _ = ffmpeg_paths(allow_fetch=False)
    kept = dedup_runs(sample_scene(ffmpeg, video, tmp_path / "out"))
    for k in range(10):
        assert any(2 * k <= c.t < 2 * k + 2 for c in kept), (k, [c.t for c in kept])


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
    assert cues and all(6.0 <= f.t <= 11.0 for f in cues)  # 2 s before to 3 s after
    assert "paste the key" in cues[0].transcript_window
    assert out.sampling.cue_terms and out.sampling.per_minute == 3
    # budget(20 s, 3/min) is 1: cue frames bypass it, plus a floor of one scene frame
    assert len(cues) > 1 and len(out.frames) == len(cues) + 1
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


@pytest.mark.parametrize(
    "media", [None, MediaInfo(path="media/a.wav", has_audio=True)], ids=["no-media", "wav"]
)
def test_frames_without_video_writes_empty_frames(tmp_path, sw_home, media):
    # localfile writes kind "file" for a .wav: no width means no video stream to sample.
    w = make_local_work(tmp_path, _fake_media(tmp_path))
    bundle = read_model(w / "ingest.json", IngestBundle)
    write_model(w / "ingest.json", bundle.model_copy(update={"media": media}))
    r = CliRunner().invoke(app, ["frames", "--work", str(w)])
    assert r.exit_code == 0, r.output
    assert read_model(w / "frames.json", FramesFile).frames == []
    assert WorkDir(w).stages().stages["frames"].status == "done"


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


# ---- R-FR-1 on the committed fixture ----

REPO = Path(__file__).resolve().parents[2]
FIXTURE_SEGMENTS = [  # tests/fixtures/tutorial-60s.en.vtt
    (1.0, 4.805, "In this tutorial we set up a tiny demo project in the terminal."),
    (9.0, 12.078, "First, type this command in the terminal and run it."),
    (16.0, 18.129, "You should see the words project ready."),
    (24.0, 27.119, "Next, paste this prompt into the prompt box."),
    (31.0, 33.332, "The assistant answers with a short poem."),
    (39.0, 41.947, "Then copy your API key into the settings panel."),
    (49.0, 51.579, "Finally, click run to see the result."),
    (55.0, 56.519, "That is the whole workflow."),
]


def _fixture_video(tmp_path: Path) -> Path:
    committed = REPO / "tests" / "fixtures" / "tutorial-60s.mp4"
    if committed.exists():
        return committed
    out = tmp_path / "tutorial-60s.mp4"
    got = subprocess.run(
        ["git", "-C", str(REPO), "show", "origin/m1/fixture:tests/fixtures/tutorial-60s.mp4"],
        capture_output=True,
        check=False,
    )
    if got.returncode != 0 or not got.stdout:
        pytest.skip("fixture video not available (M1-A not merged and no origin/m1/fixture)")
    out.write_bytes(got.stdout)
    return out


def _frame_at(video: Path, t: float, out: Path) -> Path:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-nostdin", "-ss", str(t), "-i", str(video),
         "-frames:v", "1", "-vf", "scale=1280:-2", str(out)],
        check=True,
    )  # fmt: skip
    return out


@pytest.mark.pipeline
@needs_ffmpeg
def test_r_fr_1_fixture_cues_kept_within_1s_after_appearance(tmp_path, sw_home):
    video = _fixture_video(tmp_path)
    w = make_local_work(tmp_path, video, duration=60.0)
    segments = [Segment(start=a, end=b, text=t) for a, b, t in FIXTURE_SEGMENTS]
    write_model(w / "transcript.json", Transcript(origin="captions", segments=segments))
    r = CliRunner().invoke(app, ["frames", "--work", str(w)])
    assert r.exit_code == 0, r.output
    frames = read_model(w / "frames.json", FramesFile).frames
    assert len(frames) <= 60 and len([f for f in frames if f.reason == "cue"]) >= 4
    for appear in (10.0, 25.0, 40.0, 50.0):
        before = thumbnail(_frame_at(video, appear - 1.5, tmp_path / f"before-{appear}.jpg"))
        hits = [
            f
            for f in frames
            if appear <= f.t <= appear + 1.0
            and changed_fraction(thumbnail(w / f.path), before) >= DUP_FRACTION
        ]
        assert hits, (appear, [f.t for f in frames])
