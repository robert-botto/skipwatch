"""Machine probe, capability tier and doctor report (spec 3.3, 8.1).

Doctor only looks: `--version` subprocess calls, PATH lookups, importability checks and
environment variable names. It never installs, upgrades or downloads anything (R-DOC-1), so a
missing static ffmpeg is reported as "not fetched yet" rather than fetched. The one network call
is treg's login check, `treg balance --json` (free), made only when treg is on PATH and run by
providers/content_treg.py (plan issue 11).

Every printed `uv sync` carries `--inexact`: an exact sync uninstalls extras it is not told
about, so following the yt-dlp advice would remove an installed Whisper extra. skipwatch is not
on PyPI, so without a project root the commands install from the git repository.
"""

import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Literal

import skipwatch
from skipwatch import media
from skipwatch.config import load_config
from skipwatch.errors import SkipwatchError
from skipwatch.models import DoctorComponent, DoctorMissing, DoctorReport, Tier
from skipwatch.providers import content_treg
from skipwatch.providers.whisper_common import DEFAULT_MODELS, MODEL_SIZES, hf_cached

CLOUD_KEYS = ("OPENAI_API_KEY", "GROQ_API_KEY", "DEEPGRAM_API_KEY")
YTDLP_MAX_AGE_DAYS = 60
NODE_MIN_MAJOR = 22
UV_MIN = (0, 9, 29)  # older uv panics inside the macOS sandbox
STATIC_UNFETCHED = "not fetched yet (downloads about 70 MB on first use)"
# printed before the first-run welcome; SKILL.md `## First run` keys on it verbatim
WHISPER_OFFER = "Whisper offer: "
TREG_OFF = (
    "logged in, off: set [providers.treg] enabled = true in config.toml, or pass --provider treg"
)

UvInstall = Literal["homebrew", "pipx", "pip", "standalone"]
UV_UPGRADE: dict[UvInstall, str] = {
    "homebrew": "brew upgrade uv",
    "pipx": "pipx upgrade uv",
    "pip": "pip install -U uv",
    "standalone": "uv self update",
}

FfmpegSource = Literal["system", "static", "static-unfetched", "static-broken", "none"]

TIER_ROWS: tuple[tuple[Tier, str, str], ...] = (
    (
        "0",
        "uv",
        "local files with captions, YouTube with captions, text posts, frame sampling",
    ),
    ("1", "Tier 0 plus a Whisper backend", "any video or audio without captions"),
    ("1c", "Tier 0 plus a cloud transcription key", "Tier 1 sources without local compute"),
    ("2", "Tier 1 plus node 22+ or deno", "full YouTube format list, fewer YouTube failures"),
    ("3", "Tier 1 plus treg logged in", "X threads, expanded links, download fallback"),
)
TIER_REASON: dict[Tier, str] = {
    "none": "uv not found; nothing can run",
    **{tier: unlocks for tier, _, unlocks in TIER_ROWS},
}


@dataclass
class Probe:
    uv: str | None
    python: str
    ffmpeg: str | None
    ffmpeg_source: FfmpegSource
    ytdlp: str | None
    node: str | None
    deno: str | None
    whisper_mlx: bool
    whisper_faster: bool
    apple_silicon: bool
    cloud_keys: list[str] = field(default_factory=list)
    treg_on_path: bool = False
    treg_logged_in: bool | None = None  # None when treg is not on PATH
    treg_enabled: bool = False  # [providers.treg] enabled is true or "auto" (paid calls opt-in)
    mem0_key: bool = False
    uv_install: UvInstall = "standalone"
    macos: bool = False
    whisper_model: str | None = None  # the model `auto` would load first
    whisper_model_cached: bool = False
    engine: str = skipwatch.__version__  # the code that is running, not the plugin's files


def _version_output(exe: str) -> str | None:
    path = shutil.which(exe)
    if not path:
        return None
    try:
        out = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = (out.stdout or out.stderr).splitlines()
    return lines[0].strip() if lines else None


def _second_token(line: str | None) -> str | None:
    """`uv 0.9.26 (Homebrew ...)` and `deno 2.1.0 (...)` give the version as token two."""
    if not line:
        return None
    parts = line.split()
    return parts[1] if len(parts) > 1 else None


def _probe_ffmpeg() -> tuple[str | None, FfmpegSource]:
    system = media.find_system_ffmpeg()
    if system:
        return media.ffmpeg_version(system[0]), "system"
    if media.static_ffmpeg_fetched():
        try:
            paths = media.ffmpeg_paths(allow_fetch=False)
        except SkipwatchError:
            return None, "static-broken"  # partial download, for example ffprobe missing
        return media.ffmpeg_version(paths[0]), "static"
    if importlib.util.find_spec("static_ffmpeg") is not None:
        return None, "static-unfetched"
    return None, "none"


def _ytdlp_version() -> str | None:
    try:
        return importlib.metadata.version("yt-dlp")
    except importlib.metadata.PackageNotFoundError:
        return None


def uv_install_kind(version_line: str | None, path: str | None) -> UvInstall:
    """How uv was installed, from its --version line and its resolved path."""
    where = path or ""
    if "Homebrew" in (version_line or "") or "/Cellar/" in where or "/homebrew/" in where:
        return "homebrew"
    if "/pipx/" in where:
        return "pipx"
    # A python next to uv proves nothing: the standalone installer and `uv python install
    # --default` share ~/.local/bin. Only a virtualenv or site-packages means pip.
    if "site-packages" in where or (path and (Path(path).parent.parent / "pyvenv.cfg").exists()):
        return "pip"
    return "standalone"


def _uv_path() -> str | None:
    found = shutil.which("uv")
    return str(Path(found).resolve()) if found else None


def is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def _treg_on_path() -> bool:
    return content_treg._treg_path() is not None  # one source of truth, honours the test guard


def _treg_enabled() -> bool:
    try:
        return load_config().providers.treg.enabled is not False
    except (ValueError, OSError):
        return False  # a broken config never stops doctor; ingest reports it


def probe_machine() -> Probe:
    """Look at the machine. No installs; subprocess `--version` calls, plus treg's free login
    check when treg is on PATH (the only network doctor does)."""
    ffmpeg, source = _probe_ffmpeg()
    treg = _treg_on_path()
    node = _version_output("node")
    uv_line = _version_output("uv")
    probe = Probe(
        uv=_second_token(uv_line),
        python=platform.python_version(),
        ffmpeg=ffmpeg,
        ffmpeg_source=source,
        ytdlp=_ytdlp_version(),
        node=node.lstrip("v") if node else None,
        deno=_second_token(_version_output("deno")),
        whisper_mlx=importlib.util.find_spec("mlx_whisper") is not None,
        whisper_faster=importlib.util.find_spec("faster_whisper") is not None,
        apple_silicon=is_apple_silicon(),
        cloud_keys=[key for key in CLOUD_KEYS if os.environ.get(key)],
        treg_on_path=treg,
        treg_logged_in=content_treg.logged_in() if treg else None,
        treg_enabled=_treg_enabled(),
        mem0_key=bool(os.environ.get("MEM0_API_KEY")),
        uv_install=uv_install_kind(uv_line, _uv_path()),
        macos=sys.platform == "darwin",
    )
    return with_whisper_model(probe)


def with_whisper_model(p: Probe) -> Probe:
    """Name the default Whisper model and whether it is cached: a folder check, never a
    download (plan issue 12)."""
    if p.whisper_mlx and p.apple_silicon:
        name, repo = DEFAULT_MODELS["mlx"]
    elif p.whisper_faster:
        name, repo = DEFAULT_MODELS["faster"]
    else:
        return p
    return replace(p, whisper_model=name, whisper_model_cached=hf_cached(repo))


def plugin_version(plugin_root: str | None) -> str | None:
    """The version in <plugin root>/.claude-plugin/plugin.json, or None outside a plugin."""
    if not plugin_root:
        return None
    try:
        manifest = json.loads(
            (Path(plugin_root) / ".claude-plugin/plugin.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None  # a broken manifest never stops doctor
    version = manifest.get("version") if isinstance(manifest, dict) else None
    return version if isinstance(version, str) else None


def _node_ok(version: str | None) -> bool:
    if not version:
        return False
    try:
        return int(version.split(".")[0]) >= NODE_MIN_MAJOR
    except ValueError:
        return False


def compute_tier(p: Probe) -> Tier:
    """Highest match, not a nested ladder: Tier 3 is Tier 1 plus treg logged in (plan issue
    10, M4-A3)."""
    whisper = p.whisper_mlx or p.whisper_faster
    if whisper and p.treg_logged_in:
        return "3"
    if whisper and (_node_ok(p.node) or p.deno):
        return "2"
    if whisper:
        return "1"
    if p.cloud_keys:
        return "1c"
    if p.uv:
        return "0"
    return "none"


NEXT_TIER: dict[Tier, Tier | None] = {
    "none": "0",
    "0": "1",
    "1c": "1",
    "1": "2",
    "2": "3",
    "3": None,
}


def _source_checkout_root(package_file: Path | None = None) -> Path | None:
    """The repository root when skipwatch runs from a source checkout (`src/skipwatch/`)."""
    root = Path(package_file or skipwatch.__file__).resolve().parents[2]
    return root if (root / "pyproject.toml").exists() else None


def _project_root(plugin_root: str | None) -> str | None:
    if plugin_root:
        return plugin_root
    checkout = _source_checkout_root()
    return str(checkout) if checkout else None


def _sync(root: str, flags: str = "") -> str:
    return f'uv sync --inexact --project "{root}"' + (f" {flags}" if flags else "")


def extra_command(plugin_root: str | None, extra: str) -> str:
    root = _project_root(plugin_root)
    if root:
        return _sync(root, f"--extra {extra}")
    return f'uv tool install "skipwatch[{extra}]"'


def whisper_offer(r: DoctorReport, plugin_root: str | None) -> str | None:
    """The Whisper extra a first run offers (mlx on Apple silicon, whisper elsewhere), or None
    when a backend is installed or uv is missing (the command needs uv). Printed only; the
    skill runs it after an explicit yes (M6-F)."""
    found = {c.name for c in r.components if c.found}
    if "uv" not in found or found & {"whisper-mlx", "whisper-faster"}:
        return None
    return extra_command(plugin_root, "mlx" if "apple-silicon" in found else "whisper")


def ytdlp_upgrade_command(plugin_root: str | None) -> str:
    root = _project_root(plugin_root)
    return _sync(root, "--upgrade-package yt-dlp") if root else "uv tool upgrade skipwatch"


def _reinstall_command(plugin_root: str | None, package: str | None = None) -> str:
    root = _project_root(plugin_root)
    if root:
        return _sync(root, f"--reinstall-package {package}" if package else "")
    return "uv tool install --reinstall skipwatch"


def uv_install_command() -> str:
    """The official installer for this OS, the same commands scripts/skipwatch prints."""
    curl = "curl -LsSf https://astral.sh/uv/install.sh | sh"
    if sys.platform == "darwin":
        return f"brew install uv, or: {curl}"
    if sys.platform == "win32":
        return 'powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
    return curl


def _missing_for(tier: Tier | None, p: Probe, plugin_root: str | None) -> list[DoctorMissing]:
    if tier == "0":
        return [
            DoctorMissing(
                name="uv",
                unlocks=TIER_REASON["0"],
                install_command=uv_install_command(),
            )
        ]
    if tier == "1":
        extra = "mlx" if p.apple_silicon else "whisper"
        return [
            DoctorMissing(
                name="whisper",
                unlocks=TIER_REASON["1"],
                install_command=extra_command(plugin_root, extra),
            )
        ]
    if tier == "2":
        return [
            DoctorMissing(
                name="node",
                unlocks=TIER_REASON["2"],
                install_command=(
                    f"install Node.js {NODE_MIN_MAJOR} or later from https://nodejs.org"
                ),
            )
        ]
    if tier == "3":
        return [
            DoctorMissing(
                name="treg",
                unlocks=TIER_REASON["3"],
                install_command="install the treg CLI and log in (see treg's own docs)",
            )
        ]
    return []


def _parse_ytdlp_date(version: str) -> date | None:
    try:
        year, month, day = (int(x) for x in version.split(".")[:3])
        return date(year, month, day)
    except ValueError:
        return None


def _uv_too_old(version: str | None) -> bool:
    if not version:
        return False
    try:
        parsed = tuple(int(x) for x in version.split(".")[:3])
    except ValueError:
        return False
    return parsed < UV_MIN


def _warnings(p: Probe, today: date, plugin_root: str | None) -> list[str]:
    warnings: list[str] = []
    if p.macos and _uv_too_old(p.uv):
        upgrade_uv = UV_UPGRADE[p.uv_install]
        minimum = ".".join(str(x) for x in UV_MIN)
        warnings.append(
            f"uv {p.uv} is older than {minimum} and can panic in the macOS sandbox; "
            f"run: {upgrade_uv}"
        )
    plugin = plugin_version(plugin_root)
    if plugin and plugin != p.engine:
        # A venv synced for another plugin folder (copied on update) runs that folder's code.
        warnings.append(
            f"plugin {plugin} runs engine {p.engine}; run: "
            f"{_reinstall_command(plugin_root, 'skipwatch')}"
        )
    upgrade = ytdlp_upgrade_command(plugin_root)
    if p.ytdlp is None:
        warnings.append(f"yt-dlp is not importable; run: {upgrade}")
    else:
        released = _parse_ytdlp_date(p.ytdlp)
        if released and (today - released).days > YTDLP_MAX_AGE_DAYS:
            warnings.append(
                f"yt-dlp {p.ytdlp} is older than {YTDLP_MAX_AGE_DAYS} days; run: {upgrade}"
            )
    if p.ffmpeg_source == "none":
        warnings.append(f"ffmpeg not found; run: {_reinstall_command(plugin_root)}")
    if p.ffmpeg_source == "static-broken":
        warnings.append(f"static ffmpeg is broken; {_ffmpeg_detail(p, plugin_root)}")
    return warnings


def _ffmpeg_detail(p: Probe, plugin_root: str | None) -> str:
    if p.ffmpeg_source == "static-unfetched":
        return f"static ffmpeg: {STATIC_UNFETCHED}"
    if p.ffmpeg_source == "static-broken":
        fix = _reinstall_command(plugin_root, "static-ffmpeg")
        return f"static ffmpeg broken (incomplete download); install ffmpeg on PATH or run: {fix}"
    return p.ffmpeg_source


def _whisper_model_component(p: Probe) -> list[DoctorComponent]:
    if p.whisper_model is None:
        return []
    detail = (
        "cached"
        if p.whisper_model_cached
        else f"not downloaded, about {MODEL_SIZES[p.whisper_model]}"
    )
    return [
        DoctorComponent(
            name="whisper-model",
            found=p.whisper_model_cached,
            version=p.whisper_model,
            detail=detail,
        )
    ]


def _treg_detail(p: Probe) -> str:
    if not p.treg_on_path:
        return ""
    if not p.treg_logged_in:
        return "on PATH, not logged in: run treg login"
    return "logged in" if p.treg_enabled else TREG_OFF


def _components(p: Probe, plugin_root: str | None) -> list[DoctorComponent]:
    plugin = plugin_version(plugin_root)
    return [
        DoctorComponent(name="skipwatch", found=True, version=p.engine),
        DoctorComponent(
            name="plugin",
            found=plugin is not None,
            version=plugin,
            detail="" if plugin_root else "not running from a plugin",
        ),
        DoctorComponent(name="uv", found=p.uv is not None, version=p.uv),
        DoctorComponent(name="python", found=True, version=p.python),
        DoctorComponent(
            name="ffmpeg",
            found=p.ffmpeg_source in ("system", "static"),
            version=p.ffmpeg,
            detail=_ffmpeg_detail(p, plugin_root),
        ),
        DoctorComponent(name="yt-dlp", found=p.ytdlp is not None, version=p.ytdlp),
        DoctorComponent(
            name="node",
            found=p.node is not None,
            version=p.node,
            detail="" if p.node is None or _node_ok(p.node) else f"below {NODE_MIN_MAJOR}",
        ),
        DoctorComponent(name="deno", found=p.deno is not None, version=p.deno),
        DoctorComponent(name="whisper-mlx", found=p.whisper_mlx),
        DoctorComponent(name="whisper-faster", found=p.whisper_faster),
        *_whisper_model_component(p),
        DoctorComponent(name="apple-silicon", found=p.apple_silicon),
        DoctorComponent(
            name="cloud-keys", found=bool(p.cloud_keys), detail=", ".join(p.cloud_keys)
        ),
        DoctorComponent(name="treg", found=bool(p.treg_logged_in), detail=_treg_detail(p)),
        DoctorComponent(name="mem0-key", found=p.mem0_key),
    ]


def build_report(p: Probe, today: date, plugin_root: str | None) -> DoctorReport:
    tier = compute_tier(p)
    next_tier = NEXT_TIER[tier]
    return DoctorReport(
        tier=tier,
        next_tier=next_tier,
        components=_components(p, plugin_root),
        missing=_missing_for(next_tier, p, plugin_root),
        warnings=_warnings(p, today, plugin_root),
    )


def render_table(r: DoctorReport) -> list[str]:
    lines = [f"Tier {r.tier} ({TIER_REASON[r.tier]})"]
    for tier, requires, unlocks in TIER_ROWS:
        mark = "*" if tier == r.tier else " "
        lines.append(f"{mark} {tier:<2}  {requires}: {unlocks}")
    for c in r.components:
        state = c.version or ("yes" if c.found else "no")
        detail = "" if c.name == "treg" else c.detail  # its note gets its own line below
        lines.append(f"  {c.name}: {state}" + (f" ({detail})" if detail else ""))
    for m in r.missing:
        lines.append(f"Missing for Tier {r.next_tier}: {m.name}: {m.install_command}")
    lines.extend(f"Warning: {w}" for w in r.warnings)
    lines.extend(f"treg: {c.detail}" for c in r.components if c.name == "treg" and c.detail)
    return lines
