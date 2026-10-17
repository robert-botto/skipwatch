import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch import probe as probe_module
from skipwatch.adapters.base import IngestOptions
from skipwatch.cli import app
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.media import find_system_ffmpeg
from skipwatch.models import ProbeResult
from skipwatch.probe import probe
from skipwatch.providers import content_free as cf
from skipwatch.workdir import WorkDir

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
REC = FIXTURES / "recorded" / "youtube"
URL = "https://www.youtube.com/watch?v=rE2zRhZdjFU"
needs_ffmpeg = pytest.mark.skipif(find_system_ffmpeg() is None, reason="system ffmpeg required")


def recorded(name: str = "manual-captions") -> dict:
    return json.loads((REC / f"{name}.info.json").read_text())


@pytest.fixture
def extract(monkeypatch):
    def install(info=None, error=None):
        def fake(url, opts):
            if error:
                raise cf.FreeRouteError("metadata", error)
            return info

        monkeypatch.setattr(cf, "extract", fake)

        def no_download(*args, **kwargs):
            raise AssertionError("probe must never download")

        monkeypatch.setattr(cf, "download", no_download)
        monkeypatch.setattr(cf, "download_captions", no_download)

    return install


@pytest.fixture
def no_whisper(monkeypatch):
    monkeypatch.setattr(probe_module, "_installed", lambda name: False)
    for key in ("OPENAI_API_KEY", "GROQ_API_KEY", "DEEPGRAM_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def test_probe_youtube_fixture_reports_duration_and_captions(extract, no_whisper):
    extract(recorded())
    result = probe(URL, IngestOptions())
    assert result.kind == "video" and result.platform == "youtube"
    assert result.title == "Beginner Git commands you need to know (WITH EXAMPLES)"
    assert result.author == "@GitHub" and result.duration_s == 868
    assert result.captions_available is True and result.long_video is False
    assert result.estimated_run_s == round(30 + 868 * 0.05)


def test_probe_long_video_flag_over_60_minutes(extract, no_whisper):
    extract(dict(recorded(), duration=3700))
    result = probe(URL, IngestOptions())
    assert result.long_video is True
    assert probe(URL, IngestOptions()).duration_s == 3700


def test_probe_exactly_60_minutes_is_not_long(extract, no_whisper):
    extract(dict(recorded(), duration=3600))
    assert probe(URL, IngestOptions()).long_video is False


def test_probe_estimate_without_captions_uses_the_best_local_backend(extract, monkeypatch):
    info = dict(recorded(), subtitles={}, automatic_captions={})
    extract(info)
    monkeypatch.setattr(probe_module, "_installed", lambda name: name == "faster_whisper")
    result = probe(URL, IngestOptions())
    assert result.captions_available is False
    assert result.estimated_run_s == round(30 + 868 * 0.6)
    monkeypatch.setattr(probe_module, "_installed", lambda name: name == "mlx_whisper")
    assert probe(URL, IngestOptions()).estimated_run_s == round(30 + 868 * 0.25)


def test_probe_estimate_with_only_a_cloud_key(extract, monkeypatch, no_whisper):
    extract(dict(recorded(), subtitles={}, automatic_captions={}))
    monkeypatch.setenv("GROQ_API_KEY", "x")
    assert probe(URL, IngestOptions()).estimated_run_s == round(30 + 868 * 0.1)


def test_probe_estimate_unknown_without_any_transcription_route(extract, no_whisper):
    extract(dict(recorded(), subtitles={}, automatic_captions={}))
    assert probe(URL, IngestOptions()).estimated_run_s is None


def test_probe_private_video_is_exit_4(extract):
    extract(error="ERROR: [youtube] x: Private video. Use --cookies-from-browser or --cookies")
    with pytest.raises(SkipwatchError) as e:
        probe(URL, IngestOptions())
    assert e.value.code == ExitCode.PRIVATE_CONTENT and "--cookies-from-browser" in e.value.message


def test_probe_network_failure_is_exit_3(extract):
    extract(error="ERROR: [youtube] x: Unable to download API page: HTTP Error 500")
    with pytest.raises(SkipwatchError) as e:
        probe(URL, IngestOptions())
    assert e.value.code == ExitCode.DOWNLOAD_FAILED and "free.yt-dlp.metadata" in e.value.message


def test_probe_page_without_video_is_exit_7(extract):
    extract(error="ERROR: Unsupported URL: https://example.com/post")
    with pytest.raises(SkipwatchError) as e:
        probe("https://example.com/post", IngestOptions())
    assert e.value.code == ExitCode.NO_CONTENT
    assert e.value.message == (
        "SkipWatch 0.1.0 reads videos only. This page has no video or audio. Article support "
        "is planned for a later release."
    )


def test_probe_platform_without_adapter_is_exit_2(monkeypatch):
    monkeypatch.setattr(probe_module, "adapter_for", lambda platform: None)
    with pytest.raises(SkipwatchError) as e:
        probe("https://x.com/a/status/1", IngestOptions())
    assert e.value.code == ExitCode.UNSUPPORTED_SOURCE


@needs_ffmpeg
def test_probe_local_file_with_sidecar(no_whisper):
    result = probe(str(FIXTURES / "tutorial-60s.mp4"), IngestOptions())
    assert result.kind == "file" and result.platform == "local"
    assert result.title == "tutorial-60s" and result.captions_available is True
    assert result.duration_s is not None and 59 <= result.duration_s <= 61


def test_probe_writes_nothing(tmp_path, extract, no_whisper, sw_home, monkeypatch):
    extract(recorded())
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["probe", URL])
    assert r.exit_code == 0
    assert not sw_home.exists() or not any(sw_home.rglob("*"))
    assert list(tmp_path.iterdir()) == []
    assert r.stdout == ""
    assert 'Probe: "Beginner Git commands you need to know (WITH EXAMPLES)" 14:28' in r.stderr
    assert "captions yes" in r.stderr and "est. 73s" in r.stderr


def test_probe_json_validates(extract, no_whisper, sw_home):
    extract(dict(recorded(), duration=3700))
    r = CliRunner().invoke(app, ["probe", URL, "--json"])
    assert r.exit_code == 0
    result = ProbeResult.model_validate_json(r.stdout)
    assert result.long_video is True and result.value == URL


def test_probe_cookies_flag_reaches_extract(monkeypatch, no_whisper, sw_home):
    seen = []

    def fake(url, opts):
        seen.append(opts.cookies_from_browser)
        return recorded()

    monkeypatch.setattr(cf, "extract", fake)
    r = CliRunner().invoke(app, ["probe", URL, "--cookies-from-browser", "firefox"])
    assert r.exit_code == 0 and seen == ["firefox"]


def test_probe_cli_maps_errors_to_exit_codes(extract, sw_home):
    extract(error="ERROR: [youtube] x: Private video. Use --cookies-from-browser")
    r = CliRunner().invoke(app, ["probe", URL])
    assert r.exit_code == ExitCode.PRIVATE_CONTENT and "--cookies-from-browser" in r.stderr


# ---- --work --out: the probe JSON lands in logs/ without a shell redirect (audit 5 fix 5) ----


@pytest.fixture(params=["work", "packs"])
def run_folder(request, sw_home) -> Path:
    path = sw_home / request.param / "demo-20261012-120000"
    WorkDir(path).ensure()
    return path


def test_probe_out_writes_the_json_to_logs(extract, no_whisper, run_folder):
    extract(recorded())
    out = run_folder / "logs" / "probe.json"
    r = CliRunner().invoke(app, ["probe", URL, "--work", str(run_folder), "--out", str(out)])
    assert r.exit_code == 0, r.output
    assert r.stdout == ""
    assert ProbeResult.model_validate_json(out.read_text(encoding="utf-8")).value == URL


def test_probe_out_respects_home(extract, no_whisper, tmp_path, sw_home):
    extract(recorded())
    home = tmp_path / "other" / ".skipwatch"
    work = home / "work" / "demo-20261012-120000"
    WorkDir(work).ensure()
    out = work / "logs" / "probe.json"
    args = ["--home", str(home), "probe", URL, "--work", str(work), "--out", str(out)]
    r = CliRunner().invoke(app, args)
    assert r.exit_code == 0, r.output
    assert out.is_file()


def test_probe_out_refuses_before_probing_and_writes_nothing(monkeypatch, tmp_path, run_folder):
    def no_probe(*args, **kwargs):
        raise AssertionError("a refused --out must not probe")

    monkeypatch.setattr(cf, "extract", no_probe)
    outside = tmp_path / "outside.json"
    outside.write_text("keep", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere" / "demo-20261012-120000"
    WorkDir(elsewhere).ensure()
    logs = run_folder / "logs"
    cases = [
        ["--work", str(elsewhere), "--out", str(elsewhere / "logs" / "probe.json")],
        ["--work", str(run_folder), "--out", str(outside)],
        ["--work", str(run_folder), "--out", str(logs / ".." / "stages.json")],
        ["--work", str(run_folder), "--out", str(run_folder / "probe.json")],
        ["--work", str(run_folder), "--out", str(logs)],
        ["--out", str(logs / "probe.json")],
        ["--work", str(run_folder)],
    ]
    try:
        logs.mkdir(exist_ok=True)
        (logs / "link.json").symlink_to(outside)
        (logs / "dir").symlink_to(tmp_path, target_is_directory=True)
        cases += [
            ["--work", str(run_folder), "--out", str(logs / "link.json")],
            ["--work", str(run_folder), "--out", str(logs / "dir" / "evil.json")],
        ]
    except OSError:
        pass
    stages = (run_folder / "stages.json").read_bytes()
    for args in cases:
        r = CliRunner().invoke(app, ["probe", URL, *args])
        assert r.exit_code == ExitCode.USAGE, (args, r.output)
    assert outside.read_text(encoding="utf-8") == "keep"
    assert not (tmp_path / "evil.json").exists()
    assert not (run_folder / "probe.json").exists()
    assert not (elsewhere / "logs" / "probe.json").exists()
    assert (run_folder / "stages.json").read_bytes() == stages


def test_probe_video_only_exit_names_the_reason_on_stderr(extract, capsys):
    extract(error="ERROR: Unsupported URL: https://example.com/post")
    with pytest.raises(SkipwatchError):
        probe("https://example.com/post", IngestOptions())
    err = capsys.readouterr().err
    assert "No video or audio at https://example.com/post: Unsupported URL" in err
