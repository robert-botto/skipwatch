import pytest

from skipwatch.detect import detect
from skipwatch.errors import ExitCode, SkipwatchError

CASES = [
    ("https://x.com/creator/status/123", "x"),
    ("https://twitter.com/creator/status/123?s=20", "x"),
    ("https://mobile.twitter.com/creator/status/123", "x"),
    ("https://www.youtube.com/watch?v=abc123", "youtube"),
    ("https://m.youtube.com/watch?v=abc123", "youtube"),
    ("https://youtu.be/abc123?si=share", "youtube"),
    ("https://music.youtube.com/watch?v=abc123", "youtube"),
    ("https://www.youtube.com/shorts/abc123", "youtube"),
    ("https://www.tiktok.com/@u/video/1", "tiktok"),
    ("https://vm.tiktok.com/ZMabc/", "tiktok"),
    ("https://www.instagram.com/reel/abc/", "instagram"),
    ("https://www.facebook.com/watch/?v=1", "facebook"),
    ("https://fb.watch/abc/", "facebook"),
    ("https://fb.com/u/videos/1", "facebook"),
    ("https://vimeo.com/123", "generic"),
]


@pytest.mark.parametrize("url,platform", CASES)
def test_r_det_1_url_shapes(url, platform):
    d = detect(url)
    assert (d.kind, d.platform) == ("url", platform)


def test_r_det_1_lookalike_domain_is_generic():
    assert detect("https://notyoutube.com/watch?v=1").platform == "generic"


def test_r_det_1_uppercase_host_is_matched():
    assert detect("HTTPS://WWW.YouTube.COM/watch?v=1").platform == "youtube"


def test_r_det_1_local_extensions_case_insensitive(tmp_path):
    for name in ["a.MOV", "b.mp4", "c.M4A", "d.webm", "e.Mkv", "f.OPUS"]:
        p = tmp_path / name
        p.write_bytes(b"x")
        d = detect(str(p))
        assert (d.kind, d.platform) == ("file", "local")


def test_r_det_1_local_path_with_spaces_and_unicode(tmp_path):
    d = tmp_path / "Screen Recordings é"
    d.mkdir()
    p = d / "Screen Recording 2026-10-09 at 14.02.11.mov"
    p.write_bytes(b"x")
    found = detect(str(p))
    assert (found.kind, found.platform) == ("file", "local")
    assert found.value == str(p.resolve())


def test_r_det_1_relative_path_resolved_against_cwd(tmp_path):
    (tmp_path / "clip.mp4").write_bytes(b"x")
    found = detect("clip.mp4", cwd=tmp_path)
    assert found.kind == "file" and found.value == str((tmp_path / "clip.mp4").resolve())


def test_unsupported_local_file_is_exit_2(tmp_path):
    p = tmp_path / "notes.pdf"
    p.write_bytes(b"x")
    with pytest.raises(SkipwatchError) as e:
        detect(str(p))
    assert e.value.code == ExitCode.UNSUPPORTED_SOURCE


def test_directory_is_exit_2(tmp_path):
    d = tmp_path / "folder.mp4"
    d.mkdir()
    with pytest.raises(SkipwatchError) as e:
        detect(str(d))
    assert e.value.code == ExitCode.UNSUPPORTED_SOURCE


def test_missing_path_is_exit_2(tmp_path):
    with pytest.raises(SkipwatchError) as e:
        detect(str(tmp_path / "nope.mp4"))
    assert e.value.code == ExitCode.UNSUPPORTED_SOURCE
