import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch import cli
from skipwatch.adapters.localfile import find_sidecar
from skipwatch.cli import app
from skipwatch.errors import ExitCode
from skipwatch.media import find_system_ffmpeg
from skipwatch.models import CallsFile, IngestBundle, SourceFile
from skipwatch.workdir import read_model

SYSTEM = find_system_ffmpeg()
needs_ffmpeg = pytest.mark.skipif(SYSTEM is None, reason="system ffmpeg required")
REC = "Screen Recording 2026-10-09 at 14.02.11"


def _ffmpeg(*args: str) -> None:
    assert SYSTEM is not None
    subprocess.run([str(SYSTEM[0]), "-v", "error", "-y", *args], check=True)


def make_video(path: Path, seconds: int = 2) -> None:
    _ffmpeg(
        "-f", "lavfi", "-i", f"testsrc=size=320x240:rate=10:duration={seconds}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
        "-shortest", "-pix_fmt", "yuv420p", str(path),
    )  # fmt: skip


def make_audio(path: Path, seconds: int = 2) -> None:
    _ffmpeg("-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", str(path))


def ingest(*args: str):
    return CliRunner().invoke(app, ["ingest", *args])


# ---- sidecar search (plan issue 4), no ffmpeg needed ----


def _touch(d: Path, *names: str) -> None:
    for n in names:
        (d / n).write_text("WEBVTT\n", encoding="utf-8")


def test_sidecar_prefers_english_lang_over_plain(tmp_path):
    _touch(tmp_path, "demo.mp4", "demo.vtt", "demo.en.vtt", "demo.de.vtt")
    assert find_sidecar(tmp_path / "demo.mp4") == tmp_path / "demo.en.vtt"


def test_sidecar_plain_stem_before_other_language(tmp_path):
    _touch(tmp_path, "demo.mp4", "demo.srt", "demo.de.vtt")
    assert find_sidecar(tmp_path / "demo.mp4") == tmp_path / "demo.srt"


def test_sidecar_vtt_before_srt_and_extension_case_insensitive(tmp_path):
    _touch(tmp_path, "demo.MOV", "demo.en.SRT", "demo.en-US.VTT")
    assert find_sidecar(tmp_path / "demo.MOV") == tmp_path / "demo.en-US.VTT"


def test_sidecar_other_language_as_last_resort(tmp_path):
    _touch(tmp_path, "demo.mp4", "demo.de.vtt")
    assert find_sidecar(tmp_path / "demo.mp4") == tmp_path / "demo.de.vtt"


def test_sidecar_ignores_other_stems_and_non_caption_files(tmp_path):
    _touch(tmp_path, "demo.mp4", "demo2.vtt", "demo.txt", "demo.final.cut.vtt", "other.en.vtt")
    assert find_sidecar(tmp_path / "demo.mp4") is None


def test_sidecar_with_dots_spaces_and_unicode_in_stem(tmp_path):
    _touch(tmp_path, f"{REC} é.mov", f"{REC} é.en.vtt")
    assert find_sidecar(tmp_path / f"{REC} é.mov") == tmp_path / f"{REC} é.en.vtt"


# ---- ingest command ----


@needs_ffmpeg
def test_ingest_local_with_sidecar(tmp_path):
    video = tmp_path / "demo.mp4"
    make_video(video)
    (tmp_path / "demo.en.vtt").write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello\n")
    work = tmp_path / "work"
    r = ingest(str(video), "--work", str(work), "--json")
    assert r.exit_code == 0, r.output
    bundle = json.loads(r.stdout)
    IngestBundle.model_validate(bundle)  # R-CLI-2
    assert bundle["source"]["kind"] == "file" and bundle["source"]["platform"] == "local"
    assert bundle["source"]["url"] is None and bundle["source"]["path"] == str(video.resolve())
    assert bundle["source"]["title"] == "demo"
    assert bundle["source"]["duration_s"] == pytest.approx(2.0, abs=0.2)
    media = bundle["media"]
    assert media["path"] == str(video.resolve())
    assert (media["width"], media["height"], media["has_audio"]) == (320, 240, True)
    assert media["fps"] == pytest.approx(10.0)
    assert bundle["route"] == {"context": "local", "media": "local", "fallbacks": []}
    assert bundle["context"]["captions_available"] is True
    assert bundle["context"]["captions_path"] == "captions/demo.en.vtt"
    assert (work / bundle["context"]["captions_path"]).exists()
    stages = json.loads((work / "stages.json").read_text())["stages"]
    assert stages["detect"]["status"] == "done" and stages["ingest"]["status"] == "done"
    assert read_model(work / "source.json", SourceFile).path == str(video.resolve())
    assert read_model(work / "calls.json", CallsFile).calls == []
    assert read_model(work / "ingest.json", IngestBundle).model_dump(by_alias=True) == bundle
    assert video.exists()  # the original is never moved
    assert not (work / "media").exists()  # nor copied


@needs_ffmpeg
def test_ingest_without_json_keeps_stdout_empty(tmp_path):
    video = tmp_path / "demo.mp4"
    make_video(video)
    r = ingest(str(video), "--work", str(tmp_path / "w"))
    assert r.exit_code == 0 and r.stdout == "" and r.stderr


@needs_ffmpeg
def test_ingest_local_path_with_spaces_and_unicode(tmp_path):
    d = tmp_path / "Screen Recordings é"
    d.mkdir()
    video = d / f"{REC}.mov"
    make_video(video)
    (d / f"{REC}.vtt").write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhi\n")
    work = tmp_path / "w ü"
    r = ingest(str(video), "--work", str(work), "--json")
    assert r.exit_code == 0, r.output
    bundle = json.loads(r.stdout)
    assert bundle["source"]["path"] == str(video.resolve())
    assert bundle["source"]["title"] == REC
    assert bundle["context"]["captions_path"] == f"captions/{REC}.vtt"
    assert (work / "captions" / f"{REC}.vtt").exists()


@needs_ffmpeg
def test_ingest_uppercase_extension(tmp_path):
    video = tmp_path / "CLIP.MOV"
    make_video(video)
    assert ingest(str(video), "--work", str(tmp_path / "w")).exit_code == 0


@needs_ffmpeg
def test_ingest_audio_only_file(tmp_path):
    audio = tmp_path / "talk.M4A"
    make_audio(audio)
    r = ingest(str(audio), "--work", str(tmp_path / "w"), "--json")
    assert r.exit_code == 0, r.output
    bundle = json.loads(r.stdout)
    assert bundle["source"]["kind"] == "audio"  # spec 7.1
    assert bundle["source"]["path"] == str(audio.resolve()) and bundle["source"]["url"] is None
    media = bundle["media"]
    assert media["has_audio"] is True and media["width"] is None and media["fps"] is None
    assert read_model(tmp_path / "w" / "source.json", SourceFile).kind == "audio"


@needs_ffmpeg
def test_file_without_audio_or_video_is_exit_7(tmp_path):
    srt = tmp_path / "subs.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n")
    mkv = tmp_path / "subs-only.mkv"
    _ffmpeg("-i", str(srt), "-c:s", "srt", str(mkv))
    work = tmp_path / "w"
    r = ingest(str(mkv), "--work", str(work))
    assert r.exit_code == 7, r.output
    assert json.loads((work / "stages.json").read_text())["stages"]["ingest"]["status"] == "failed"
    assert not (work / "ingest.json").exists()


@needs_ffmpeg
def test_unreadable_media_is_exit_2(tmp_path):
    bad = tmp_path / "broken.mp4"
    bad.write_bytes(b"not a video")
    r = ingest(str(bad), "--work", str(tmp_path / "w"))
    assert r.exit_code == 2 and "Traceback" not in r.output


def test_url_in_m1_is_exit_2(tmp_path):
    r = ingest("https://youtu.be/x", "--work", str(tmp_path / "w"))
    assert r.exit_code == 2
    assert "M2" in r.stderr


def test_unsupported_file_is_exit_2_and_detect_failed(tmp_path):
    pdf = tmp_path / "notes.pdf"
    pdf.write_bytes(b"x")
    work = tmp_path / "w"
    r = ingest(str(pdf), "--work", str(work))
    assert r.exit_code == 2
    assert json.loads((work / "stages.json").read_text())["stages"]["detect"]["status"] == "failed"


def test_ingest_accepts_contract_flags(tmp_path):
    r = ingest(
        "https://youtu.be/x", "--work", str(tmp_path / "w"), "--provider", "free",
        "--max-height", "720", "--cookies-from-browser", "firefox",
    )  # fmt: skip
    assert r.exit_code == 2  # flags parsed; the URL itself is M2


def test_ingest_unknown_provider_is_usage_exit_64(tmp_path, monkeypatch, capsys):
    args = ["skipwatch", "ingest", "https://youtu.be/x", "--work", str(tmp_path / "w")]
    monkeypatch.setattr(sys, "argv", [*args, "--provider", "paid"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == ExitCode.USAGE
    assert not (tmp_path / "w").exists()


@needs_ffmpeg
def test_r_cli_1_ingest_idempotent(tmp_path):
    video = tmp_path / "demo.mp4"
    make_video(video)
    (tmp_path / "demo.en.vtt").write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello\n")
    work = tmp_path / "w"
    for _ in range(2):
        assert ingest(str(video), "--work", str(work)).exit_code == 0
    first = {n: (work / n).read_bytes() for n in ("ingest.json", "source.json", "calls.json")}
    assert ingest(str(video), "--work", str(work)).exit_code == 0
    assert {n: (work / n).read_bytes() for n in first} == first


@needs_ffmpeg
def test_audio_with_cover_art_is_audio_kind(tmp_path):
    raw = tmp_path / "raw.wav"
    make_audio(raw)
    cover = tmp_path / "cover.png"
    _ffmpeg("-f", "lavfi", "-i", "color=c=red:size=64x64", "-frames:v", "1", str(cover))
    song = tmp_path / "episode.mp3"
    _ffmpeg(
        "-i", str(raw), "-i", str(cover), "-map", "0", "-map", "1",
        "-c:v", "mjpeg", "-disposition:v", "attached_pic", str(song),
    )  # fmt: skip
    r = ingest(str(song), "--work", str(tmp_path / "w"), "--json")
    assert r.exit_code == 0, r.output
    bundle = json.loads(r.stdout)
    assert bundle["source"]["kind"] == "audio" and bundle["media"]["width"] is None
