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
    assert whisper.install_command == 'uv sync --inexact --project "/plug" --extra mlx'
    lines = doctor.render_table(r)
    assert lines[0].startswith("Tier 0 (")
    assert any(line.startswith("Missing for Tier 1: whisper: uv sync") for line in lines)


def test_every_printed_uv_sync_is_inexact(monkeypatch):
    # An exact `uv sync` uninstalls extras it is not told about (following the yt-dlp advice
    # removed the whisper extra), so every sync doctor prints must carry --inexact.
    probes = [
        P(ytdlp="2026.01.01", ffmpeg=None, ffmpeg_source="none"),
        P(apple_silicon=False, ytdlp=None),
        P(ffmpeg=None, ffmpeg_source="static-broken"),
    ]
    for root in ("/plug", None):
        for probe in probes:
            r = doctor.build_report(probe, TODAY, plugin_root=root)
            commands = (
                [m.install_command for m in r.missing]
                + r.warnings
                + [c.detail for c in r.components]
            )
            syncs = [c for c in commands if "uv sync" in c]
            assert syncs, (root, probe)
            assert all("uv sync --inexact" in c for c in syncs), syncs


def test_install_commands_without_plugin_root_use_source_checkout(monkeypatch, tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    monkeypatch.setattr(doctor, "_source_checkout_root", lambda: tmp_path)
    r = doctor.build_report(P(apple_silicon=False), TODAY, plugin_root=None)
    whisper = next(m for m in r.missing if m.name == "whisper")
    assert whisper.install_command == f'uv sync --inexact --project "{tmp_path}" --extra whisper'


def test_install_commands_without_any_root_use_git_not_pypi(monkeypatch):
    monkeypatch.setattr(doctor, "_source_checkout_root", lambda: None)
    r = doctor.build_report(P(), TODAY, plugin_root=None)
    whisper = next(m for m in r.missing if m.name == "whisper")
    assert whisper.install_command == (
        'uv tool install "skipwatch[mlx] @ git+https://github.com/robert-botto/skipwatch"'
    )
    old = doctor.build_report(P(ytdlp="2026.01.01"), TODAY, plugin_root=None)
    assert any("uv tool upgrade skipwatch" in w for w in old.warnings)


def test_source_checkout_root_detection(tmp_path):
    pkg = tmp_path / "src" / "skipwatch" / "__init__.py"
    pkg.parent.mkdir(parents=True)
    pkg.write_text("")
    assert doctor._source_checkout_root(pkg) is None
    (tmp_path / "pyproject.toml").write_text("")
    assert doctor._source_checkout_root(pkg) == tmp_path


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
    assert sum("login not verified" in line for line in lines) == 1


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


def test_r_tier_1_broken_static_ffmpeg_still_exits_zero(monkeypatch, sw_home):
    def no_fetch():
        raise AssertionError("fetched")

    monkeypatch.setattr(doctor.media, "find_system_ffmpeg", lambda: None)
    monkeypatch.setattr(doctor.media, "static_ffmpeg_fetched", lambda: True)
    monkeypatch.setattr(doctor.media, "_static_paths_on_disk", lambda: None)  # ffprobe missing
    monkeypatch.setattr(doctor.media, "_fetch_static", no_fetch)
    r = CliRunner().invoke(app, ["doctor", "--json"])
    assert r.exit_code == 0, r.output
    report = DoctorReport.model_validate_json(r.stdout)
    ffmpeg = next(c for c in report.components if c.name == "ffmpeg")
    assert not ffmpeg.found and "broken" in ffmpeg.detail
    assert "--reinstall-package static-ffmpeg" in ffmpeg.detail


def test_extra_command_is_public():
    assert doctor.extra_command("/plug", "whisper") == (
        'uv sync --inexact --project "/plug" --extra whisper'
    )


def test_old_uv_on_macos_warns_with_upgrade_command_for_its_install():
    cases = {
        "homebrew": "brew upgrade uv",
        "pipx": "pipx upgrade uv",
        "pip": "pip install -U uv",
        "standalone": "uv self update",
    }
    for install, command in cases.items():
        r = doctor.build_report(P(uv="0.9.26", uv_install=install, macos=True), TODAY, "/plug")
        assert any("uv 0.9.26" in w and command in w for w in r.warnings), install
    for fine in ("0.9.29", "0.10.0", "1.0.0", None, "dev"):
        r = doctor.build_report(P(uv=fine, macos=True), TODAY, "/plug")
        assert not any(w.startswith("uv ") for w in r.warnings), fine


def test_old_uv_off_macos_no_warning_but_version_shown():
    r = doctor.build_report(P(uv="0.9.26", macos=False), TODAY, "/plug")
    assert not any(w.startswith("uv ") for w in r.warnings)
    uv = next(c for c in r.components if c.name == "uv")
    assert uv.found and uv.version == "0.9.26"


def test_uv_install_kind_from_version_line_and_path(tmp_path):
    def kind(line, path):
        return doctor.uv_install_kind(line, path)

    assert kind("uv 0.9.26 (Homebrew 2026-01-15)", None) == "homebrew"
    assert kind("uv 0.9.26", "/opt/homebrew/Cellar/uv/0.9.26/bin/uv") == "homebrew"
    assert kind("uv 0.9.26", "/Users/a/.local/pipx/venvs/uv/bin/uv") == "pipx"
    assert kind("uv 0.9.26", "/Users/a/Library/Application Support/pipx/venvs/uv/bin/uv") == (
        "pipx"
    )
    venv_bin = tmp_path / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    (tmp_path / "venv" / "pyvenv.cfg").write_text("")
    assert kind("uv 0.9.26", str(venv_bin / "uv")) == "pip"
    # The standalone installer and `uv python install --default` share ~/.local/bin.
    local_bin = tmp_path / "home" / ".local" / "bin"
    local_bin.mkdir(parents=True)
    (local_bin / "uv").write_text("")
    (local_bin / "python3").write_text("")
    assert kind("uv 0.9.26", str(local_bin / "uv")) == "standalone"
    assert kind("uv 0.9.26", "/usr/lib/python3/site-packages/uv/bin/uv") == "pip"
    assert kind("uv 0.9.30 (abc 2026-10-01)", str(tmp_path / "local" / "uv")) == "standalone"


def test_probe_detects_uv_install_and_macos(monkeypatch):
    lines = {"uv": "uv 0.9.26 (Homebrew 2026-01-15)"}
    monkeypatch.setattr(doctor, "_version_output", lambda exe: lines.get(exe))
    monkeypatch.setattr(doctor.sys, "platform", "darwin")
    p = doctor.probe_machine()
    assert p.uv == "0.9.26" and p.uv_install == "homebrew" and p.macos is True
    monkeypatch.setattr(doctor.sys, "platform", "linux")
    assert doctor.probe_machine().macos is False
