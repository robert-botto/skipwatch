from pathlib import Path

import pytest

from skipwatch import media
from skipwatch.errors import ExitCode, SkipwatchError


def _no_fetch():
    raise AssertionError("static ffmpeg fetch must not run")


def test_prefers_system_ffmpeg(monkeypatch):
    monkeypatch.setattr(media.shutil, "which", lambda n: f"/usr/bin/{n}")
    monkeypatch.setattr(media, "_fetch_static", _no_fetch)
    assert media.ffmpeg_paths(allow_fetch=False) == (
        Path("/usr/bin/ffmpeg"),
        Path("/usr/bin/ffprobe"),
    )


def test_missing_ffmpeg_without_fetch_is_exit_8(monkeypatch):
    monkeypatch.setattr(media.shutil, "which", lambda n: None)
    monkeypatch.setattr(media, "static_ffmpeg_fetched", lambda: False)
    monkeypatch.setattr(media, "_fetch_static", _no_fetch)
    with pytest.raises(SkipwatchError) as exc:
        media.ffmpeg_paths(allow_fetch=False)
    assert exc.value.code == ExitCode.MISSING_DEPENDENCY
    assert "uv sync --project" in exc.value.message


def test_missing_system_ffmpeg_fetches_static_when_allowed(monkeypatch):
    monkeypatch.setattr(media.shutil, "which", lambda n: None)
    monkeypatch.setattr(media, "static_ffmpeg_fetched", lambda: False)
    monkeypatch.setattr(media, "_fetch_static", lambda: (Path("/s/ffmpeg"), Path("/s/ffprobe")))
    assert media.ffmpeg_paths() == (Path("/s/ffmpeg"), Path("/s/ffprobe"))


def test_system_ffmpeg_needs_ffprobe_too(monkeypatch):
    monkeypatch.setattr(
        media.shutil, "which", lambda n: "/usr/bin/ffmpeg" if n == "ffmpeg" else None
    )
    assert media.find_system_ffmpeg() is None


def test_static_ffmpeg_fetched_reads_disk_only(monkeypatch, tmp_path):
    monkeypatch.setattr(media, "_static_bin_dir", lambda: tmp_path / "bin")
    assert media.static_ffmpeg_fetched() is False
    (tmp_path / "bin" / "darwin").mkdir(parents=True)
    assert media.static_ffmpeg_fetched() is False
    (tmp_path / "bin" / "darwin" / "ffmpeg").write_text("")
    assert media.static_ffmpeg_fetched() is True


def test_version_parse():
    assert media.parse_ffmpeg_version("ffmpeg version 7.0 Copyright (c) 2000-2024") == "7.0"
    assert media.parse_ffmpeg_version("something else") is None


needs_ffmpeg = pytest.mark.skipif(media.find_system_ffmpeg() is None, reason="no ffmpeg on PATH")


@needs_ffmpeg
def test_real_ffmpeg_version_and_filters():
    ffmpeg, _ = media.ffmpeg_paths(allow_fetch=False)
    assert media.ffmpeg_version(ffmpeg)
    assert media.has_filter(ffmpeg, "showinfo")
    assert not media.has_filter(ffmpeg, "no_such_filter_xyz")


def test_ffmpeg_version_of_missing_binary_is_none(tmp_path):
    assert media.ffmpeg_version(tmp_path / "nope") is None


@needs_ffmpeg
def test_probe_reads_streams(tmp_path):
    import subprocess

    ffmpeg, _ = media.ffmpeg_paths(allow_fetch=False)
    clip = tmp_path / "clip one é.mp4"
    subprocess.run(
        [str(ffmpeg), "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x48:d=1", str(clip)],
        check=True,
    )
    info = media.probe(clip)
    assert info["streams"][0]["width"] == 64


@needs_ffmpeg
def test_probe_unreadable_file_is_exit_2(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_text("not a video")
    with pytest.raises(SkipwatchError) as exc:
        media.probe(bad)
    assert exc.value.code == ExitCode.UNSUPPORTED_SOURCE
