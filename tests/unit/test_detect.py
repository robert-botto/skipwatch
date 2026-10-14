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
    ("https://www.youtube-nocookie.com/embed/abc123", "youtube"),
    ("https://instagr.am/p/abc/", "instagram"),
    ("https://t.co/abc", "generic"),  # a redirect; resolving it needs the network (M2)
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


@pytest.mark.parametrize(
    "value,platform",
    [
        ("youtube.com/watch?v=abc123", "youtube"),
        ("www.youtube.com/watch?v=abc123", "youtube"),
        ("x.com/u/status/1", "x"),
        ("youtu.be/abc123", "youtube"),
        ("vimeo.com/123", "generic"),
        ("example.com?v=1", "generic"),  # anything but a lone "/" after the host
    ],
)
def test_r_det_1_scheme_less_urls(tmp_path, value, platform):
    d = detect(value, cwd=tmp_path)
    assert (d.kind, d.platform, d.value) == ("url", platform, "https://" + value)


@pytest.mark.parametrize("value", ["nope.mp4", "clip.mov", "talk.M4A", "notes", "a/b.mp4"])
def test_missing_media_file_names_are_not_treated_as_urls(tmp_path, value):
    with pytest.raises(SkipwatchError) as e:
        detect(value, cwd=tmp_path)
    assert e.value.code == ExitCode.UNSUPPORTED_SOURCE


def test_existing_path_wins_over_domain_shape(tmp_path):
    (tmp_path / "youtube.com").mkdir()
    (tmp_path / "youtube.com" / "clip.mp4").write_bytes(b"x")
    assert detect("youtube.com/clip.mp4", cwd=tmp_path).kind == "file"


@pytest.mark.parametrize(
    "value",
    ["m.youtube.com/watch?v=abc123", "WWW.YouTube.com/watch?v=abc123", "youtube.com"],
)
def test_scheme_less_youtube_variants_are_urls(tmp_path, value):
    d = detect(value, cwd=tmp_path)
    assert (d.kind, d.platform, d.value) == ("url", "youtube", "https://" + value)


def test_scheme_less_url_with_surrounding_space_is_stripped(tmp_path):
    d = detect("  youtube.com/watch?v=abc123 ", cwd=tmp_path)
    assert d.value == "https://youtube.com/watch?v=abc123"


def test_dot_slash_media_file_resolves_as_file(tmp_path):
    (tmp_path / "clip.mp4").write_bytes(b"x")
    found = detect("./clip.mp4", cwd=tmp_path)
    assert (found.kind, found.platform) == ("file", "local")


def test_existing_dotted_file_is_a_file_not_a_url(tmp_path):
    """notes.md has a domain shape (.md is a TLD) but exists, so it is judged as a file."""
    (tmp_path / "notes.md").write_text("x")
    with pytest.raises(SkipwatchError) as e:
        detect("notes.md", cwd=tmp_path)
    assert e.value.code == ExitCode.UNSUPPORTED_SOURCE
    assert "unsupported file type .md" in str(e.value)


@pytest.mark.parametrize("value", ["./clip.mp4", "my clip.com/x", "youtube .com/watch"])
def test_missing_paths_without_a_domain_shape_are_exit_2(tmp_path, value):
    with pytest.raises(SkipwatchError) as e:
        detect(value, cwd=tmp_path)
    assert e.value.code == ExitCode.UNSUPPORTED_SOURCE
    assert "no such file" in str(e.value)


@pytest.mark.parametrize(
    "value",
    [
        "notes.md",
        "report.pdf",
        "clip.mp4",
        "notes.txt",
        "example.com",
        "notes.md/",
        "example.com/",
        "vimeo.com",  # vimeo has no adapter of its own: generic, so a bare name is a file
    ],
)
def test_missing_bare_name_is_a_missing_file_not_a_url(tmp_path, value):
    # Ruling FU-R1: a missing notes.md must not become a request to https://notes.md. With no
    # "/" after it, only a known platform host is read as a URL.
    with pytest.raises(SkipwatchError) as e:
        detect(value, cwd=tmp_path)
    assert e.value.code == ExitCode.UNSUPPORTED_SOURCE
    assert "no such file" in str(e.value)


@pytest.mark.parametrize(
    "value,platform",
    [
        ("youtube.com/watch?v=x", "youtube"),
        ("www.youtube.com/watch?v=x", "youtube"),
        ("youtu.be/x", "youtube"),
        ("x.com/u/status/1", "x"),
        ("example.com/post", "generic"),
        ("youtube.com", "youtube"),
        ("www.tiktok.com", "tiktok"),
        ("youtube.com?v=x", "youtube"),
        ("x.com", "x"),
        ("example.com/talk", "generic"),
        ("vimeo.com/123", "generic"),
    ],
)
def test_scheme_less_known_host_or_path_is_a_url(tmp_path, value, platform):
    d = detect(value, cwd=tmp_path)
    assert (d.kind, d.platform, d.value) == ("url", platform, "https://" + value)


@pytest.mark.parametrize("value", ["notes.md", "example.com", "notes.md/"])
def test_missing_domain_like_name_hints_at_https(tmp_path, value):
    with pytest.raises(SkipwatchError) as e:
        detect(value, cwd=tmp_path)
    assert str(e.value) == f"not a URL and no such file: {value} (include https:// for a web link)"


@pytest.mark.parametrize("value", ["clip.mp4", "./notes.md", "my notes", "a/b.md"])
def test_missing_plain_name_has_no_https_hint(tmp_path, value):
    with pytest.raises(SkipwatchError) as e:
        detect(value, cwd=tmp_path)
    assert str(e.value) == f"not a URL and no such file: {value}"


def test_existing_folder_with_a_domain_like_name_has_no_https_hint(tmp_path):
    # notes.md is there, just not a file: telling the user to add https:// would mislead.
    (tmp_path / "notes.md").mkdir()
    with pytest.raises(SkipwatchError) as e:
        detect("notes.md", cwd=tmp_path)
    assert e.value.code == ExitCode.UNSUPPORTED_SOURCE
    assert str(e.value) == "not a URL and no such file: notes.md"
