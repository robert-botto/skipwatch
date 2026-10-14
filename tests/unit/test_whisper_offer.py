"""First run: doctor offers the platform's Whisper extra once, and the skill asks once."""

import re
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch import doctor, firstrun
from skipwatch.cli import app

ROOT = Path(__file__).resolve().parents[2]
SKILL_MD = ROOT / "skills/skipwatch/SKILL.md"
BANNER_MD = ROOT / "skills/skipwatch/references/first-run-banner.md"
BASE = dict(
    uv="0.9.30",
    python="3.12.12",
    ffmpeg="8.0.1",
    ffmpeg_source="system",
    ytdlp="2026.10.01",
    node=None,
    deno=None,
    whisper_mlx=False,
    whisper_faster=False,
    apple_silicon=True,
    cloud_keys=[],
    treg_on_path=False,
    mem0_key=False,
)


def P(**kw):
    return doctor.Probe(**(BASE | kw))


def _doctor(monkeypatch, probe, *args):
    monkeypatch.setattr(doctor, "probe_machine", lambda: probe)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/plug")
    result = CliRunner().invoke(app, ["doctor", "--json", *args])
    assert result.exit_code == 0, result.output
    return result.stderr.splitlines()


def _offers(lines):
    return [line for line in lines if line.startswith(doctor.WHISPER_OFFER)]


@pytest.mark.parametrize(("apple", "extra"), [(True, "--extra mlx"), (False, "--extra whisper")])
def test_first_run_offers_the_platform_extra_before_the_welcome(sw_home, monkeypatch, apple, extra):
    lines = _doctor(monkeypatch, P(apple_silicon=apple))
    assert lines[-1] == firstrun.WELCOME  # SKILL.md still keys on the last line
    flags = f"{extra} --locked --quiet --no-dev"
    assert lines[-2] == f'{doctor.WHISPER_OFFER}uv sync --inexact --project "/plug" {flags}'


def test_offer_is_printed_once_per_home(sw_home, monkeypatch):
    assert len(_offers(_doctor(monkeypatch, P()))) == 1
    assert _offers(_doctor(monkeypatch, P())) == []  # asked once, never again
    assert _offers(_doctor(monkeypatch, P(), "--max-age-hours", "24")) == []


@pytest.mark.parametrize(
    "probe",
    [
        P(whisper_mlx=True),
        P(whisper_faster=True),
        P(apple_silicon=False, whisper_faster=True),
        P(uv=None),  # the command needs uv; the uv advice comes first
    ],
)
def test_no_offer_when_whisper_is_installed_or_uv_is_missing(sw_home, monkeypatch, probe):
    lines = _doctor(monkeypatch, probe)
    assert lines[-1] == firstrun.WELCOME and _offers(lines) == []


def test_cloud_key_still_gets_the_local_offer(sw_home, monkeypatch):
    assert len(_offers(_doctor(monkeypatch, P(cloud_keys=["OPENAI_API_KEY"])))) == 1


def test_offer_from_a_cached_report(sw_home, monkeypatch):
    # a doctor.json written before the marker (an older engine) still yields the offer
    report = doctor.build_report(P(apple_silicon=False), date.today(), "/plug")
    sw_home.mkdir(parents=True)
    (sw_home / "doctor.json").write_text(report.model_dump_json(by_alias=True), "utf-8")
    monkeypatch.setattr(doctor, "probe_machine", lambda: pytest.fail("cache not used"))
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/plug")
    result = CliRunner().invoke(app, ["doctor", "--json", "--max-age-hours", "24"])
    assert result.exit_code == 0, result.output
    flags = "--extra whisper --locked --quiet --no-dev"
    offer = f'{doctor.WHISPER_OFFER}uv sync --inexact --project "/plug" {flags}'
    assert result.stderr.splitlines()[-2:] == [offer, firstrun.WELCOME]


def test_offer_never_runs_anything(sw_home, monkeypatch):
    import subprocess

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail(f"ran {a}"))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail(f"ran {a}"))
    assert len(_offers(_doctor(monkeypatch, P()))) == 1


def test_offer_skips_dev_tools_exactly_as_the_wrapper_does(tmp_path):
    # scripts/skipwatch syncs with --no-dev unless the root has .git (marketplace installs
    # have none), so the offer must not pull pytest, ruff and pyright into a plugin venv
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    assert doctor.extra_command(str(plugin), "mlx").split()[-1] == "--no-dev"
    (plugin / ".git").mkdir()
    assert "--no-dev" not in doctor.extra_command(str(plugin), "mlx")
    wrapper = (ROOT / "scripts/skipwatch").read_text(encoding="utf-8")
    assert '[ -e "$root/.git" ] || sync_args="$sync_args --no-dev"' in wrapper


@pytest.mark.parametrize(
    "command",
    [
        lambda root: doctor.extra_command(root, "whisper"),
        doctor.ytdlp_upgrade_command,
        doctor._reinstall_command,
        lambda root: doctor._reinstall_command(root, "static-ffmpeg"),
    ],
)
def test_every_printed_sync_skips_dev_tools_like_the_wrapper(tmp_path, command):
    # the .git decision lives in _sync, so no advice pulls the dev group into a plugin venv
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    assert command(str(plugin)).endswith(" --no-dev")
    (plugin / ".git").mkdir()
    assert "--no-dev" not in command(str(plugin))


def test_offer_uses_the_wrappers_sync_flags(tmp_path):
    # the same flags as scripts/skipwatch's own sync: --locked never rewrites the shipped
    # uv.lock inside the plugin folder (M6F-FR1 minor 4)
    wrapper = (ROOT / "scripts/skipwatch").read_text(encoding="utf-8")
    wrapper_flags = set(re.search(r'^sync_args="([^"]+)"', wrapper, re.M).group(1).split())
    assert wrapper_flags == {"--quiet", "--locked", "--inexact"}
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    flags = {w for w in doctor.extra_command(str(plugin), "mlx").split() if w.startswith("--")}
    assert flags == wrapper_flags | {"--no-dev", "--project", "--extra"}


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_skill_asks_once_and_installs_only_on_yes():
    skill = SKILL_MD.read_text(encoding="utf-8")
    first_run = _flat(skill.split("\n## First run\n", 1)[1].split("\n## ", 1)[0])
    assert f"`{doctor.WHISPER_OFFER.strip()}`" in first_run
    assert "`## Whisper offer`" in first_run and "before anything else runs" in first_run
    # the offer text lives in the file read once per home, outside the per-run word budget
    offer = _flat(BANNER_MD.read_text(encoding="utf-8").split("\n## Whisper offer\n", 1)[1])
    assert f"`{doctor.WHISPER_OFFER}`" in offer
    assert "Ask once and wait" in offer and "Only on an explicit yes" in offer
    assert "Never ask again" in offer
    # a refreshed report after the install, so stage 1's tier is not a stale cache
    assert "`<ENGINE> doctor --json`" in offer
    # a no or a failed install keeps the run going: captions first, then frames only
    assert "captions first, then frames only" in offer and "never a traceback" in offer
    # a declined permission prompt has no exit code to print
    assert "with its exit code, if any" in offer


def test_offer_is_never_asked_under_yes():
    # an unattended --yes run must not stall on the offer; doctor still uses up the marker
    # and its "Missing for Tier 1" line keeps naming the command (M6F-FR1 I1)
    skill = SKILL_MD.read_text(encoding="utf-8")
    first_run = _flat(skill.split("\n## First run\n", 1)[1].split("\n## ", 1)[0])
    assert "without `--yes`" in first_run and "doctor keeps listing the command" in first_run
    rules = _flat(skill.split("\n## Rules that hold in every stage\n", 1)[1])
    assert "The first-run Whisper offer comes before the run and is also never asked" in rules


def test_doctor_command_does_not_offer_whisper_twice():
    # `/skipwatch doctor` as the first command: the first-run offer already asked
    skill = SKILL_MD.read_text(encoding="utf-8")
    section = _flat(skill.split("\n## doctor\n", 1)[1].split("\n## ", 1)[0])
    assert "except Whisper when the Whisper offer was just asked" in section


def test_no_em_dash_in_offer_sources():
    for path in (SKILL_MD, BANNER_MD, Path(doctor.__file__), Path(__file__)):
        assert chr(0x2014) not in path.read_text(encoding="utf-8"), path
    assert re.fullmatch(r"[A-Za-z ]+: ", doctor.WHISPER_OFFER)
