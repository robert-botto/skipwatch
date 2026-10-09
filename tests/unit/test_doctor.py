from datetime import date

from typer.testing import CliRunner

from skipwatch import doctor
from skipwatch.cli import app
from skipwatch.models import DoctorReport

BASE = dict(
    uv="0.9.26",
    python="3.12.12",
    ffmpeg="8.0.1",
    ffmpeg_source="system",
    ytdlp="2026.08.19",
    node=None,
    deno=None,
    whisper_mlx=False,
    whisper_faster=False,
    apple_silicon=True,
    cloud_keys=[],
    treg_on_path=False,
    mem0_key=False,
)
TODAY = date(2026, 10, 9)


def P(**kw):
    return doctor.Probe(**(BASE | kw))


def test_tier_ladder():
    assert doctor.compute_tier(P(uv=None)) == "none"
    assert doctor.compute_tier(P()) == "0"
    assert doctor.compute_tier(P(cloud_keys=["OPENAI_API_KEY"])) == "1c"
    assert doctor.compute_tier(P(whisper_faster=True)) == "1"
    assert doctor.compute_tier(P(whisper_mlx=True, node="25.4.0")) == "2"
    assert doctor.compute_tier(P(whisper_mlx=True, deno="2.1.0")) == "2"
    assert doctor.compute_tier(P(whisper_mlx=True, node="20.1.0")) == "1"  # node below 22
    assert doctor.compute_tier(P(whisper_faster=True, treg_on_path=True)) == "3"
    assert doctor.compute_tier(P(treg_on_path=True)) == "0"  # treg without whisper is not Tier 3


def test_r_tier_1_report_names_next_tier_and_command():
    r = doctor.build_report(P(), TODAY, plugin_root="/plug")
    assert r.tier == "0" and r.next_tier == "1"
    whisper = next(m for m in r.missing if m.name == "whisper")
    assert whisper.install_command == 'uv sync --project "/plug" --extra mlx'  # Apple Silicon
    lines = doctor.render_table(r)
    assert lines[0].startswith("Tier 0 (")
    assert any(line.startswith("Missing for Tier 1: whisper: uv sync") for line in lines)


def test_r_tier_1_install_commands_without_plugin_root():
    r = doctor.build_report(P(apple_silicon=False), TODAY, plugin_root=None)
    whisper = next(m for m in r.missing if m.name == "whisper")
    assert whisper.install_command == 'uv tool install "skipwatch[whisper]"'


def test_r_tier_1_every_tier_has_next_step_until_3():
    cases = {
        "none": P(uv=None),
        "1c": P(cloud_keys=["GROQ_API_KEY"]),
        "1": P(whisper_faster=True),
        "2": P(whisper_faster=True, node="22.0.0"),
    }
    for tier, probe in cases.items():
        r = doctor.build_report(probe, TODAY, plugin_root="/plug")
        assert r.tier == tier
        assert r.next_tier is not None and r.missing, tier
        assert all(m.install_command for m in r.missing)
    node = doctor.build_report(cases["1"], TODAY, "/plug").missing[0]
    assert "https://nodejs.org" in node.install_command
    top = doctor.build_report(P(whisper_faster=True, treg_on_path=True), TODAY, "/plug")
    assert top.tier == "3" and top.next_tier is None and top.missing == []


def test_r_doc_2_old_ytdlp_warns_with_upgrade_command():
    r = doctor.build_report(P(ytdlp="2026.07.01"), TODAY, plugin_root="/plug")
    assert any("yt-dlp" in w and "--upgrade-package yt-dlp" in w for w in r.warnings)
    fresh = doctor.build_report(P(ytdlp="2026.9.20"), TODAY, plugin_root="/plug")
    assert not any("yt-dlp" in w for w in fresh.warnings)


def test_static_unfetched_ffmpeg_reported_not_fetched():
    r = doctor.build_report(P(ffmpeg=None, ffmpeg_source="static-unfetched"), TODAY, "/plug")
    assert any("not fetched yet" in line for line in doctor.render_table(r))


def test_treg_login_not_verified_and_key_values_never_shown():
    p = P(whisper_faster=True, treg_on_path=True, cloud_keys=["OPENAI_API_KEY"])
    lines = doctor.render_table(doctor.build_report(p, TODAY, "/plug"))
    assert "treg: on PATH, login not verified" in lines


def test_cloud_keys_reported_by_name_only(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value-123")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    p = doctor.probe_machine()
    assert p.cloud_keys == ["OPENAI_API_KEY"]
    r = doctor.build_report(p, TODAY, None)
    assert "sk-secret-value-123" not in r.model_dump_json()


def test_r_doc_1_doctor_never_fetches_or_installs(monkeypatch, sw_home):
    calls = []
    real_run = doctor.subprocess.run

    def spy(cmd, *a, **k):
        calls.append(cmd)
        return real_run(cmd, *a, **k)

    def no_fetch():
        raise AssertionError("fetched")

    monkeypatch.setattr(doctor.subprocess, "run", spy)
    monkeypatch.setattr(doctor.media, "_fetch_static", no_fetch)
    monkeypatch.setattr(doctor.media.shutil, "which", lambda n: None)  # force the static path
    r = CliRunner().invoke(app, ["doctor"])
    assert r.exit_code == 0, r.output
    for cmd in calls:
        joined = " ".join(map(str, cmd))
        assert not any(w in joined for w in ("install", "sync", "pip", "brew")), joined


def test_r_tier_1_doctor_exits_zero_and_prints_tier(sw_home):
    r = CliRunner().invoke(app, ["doctor", "--json"])
    assert r.exit_code == 0
    DoctorReport.model_validate_json(r.stdout)  # R-CLI-2
    assert r.stderr.startswith("Tier ")
    assert (sw_home / "doctor.json").exists()


def test_doctor_without_json_keeps_stdout_empty(sw_home):
    r = CliRunner().invoke(app, ["doctor"])
    assert r.exit_code == 0 and r.stdout == ""
