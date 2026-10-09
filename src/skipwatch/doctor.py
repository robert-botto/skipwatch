"""Machine probe, capability tier and doctor report (spec 3.3, 8.1).

Doctor only looks: `--version` subprocess calls, PATH lookups, importability checks and
environment variable names. It never installs, upgrades or downloads anything (R-DOC-1), so a
missing static ffmpeg is reported as "not fetched yet" rather than fetched. treg login needs a
network call, so M0 reports "on PATH, login not verified" (plan issue 11).
"""

import importlib.metadata
import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from skipwatch import media
from skipwatch.models import DoctorComponent, DoctorMissing, DoctorReport, Tier

CLOUD_KEYS = ("OPENAI_API_KEY", "GROQ_API_KEY", "DEEPGRAM_API_KEY")
YTDLP_MAX_AGE_DAYS = 60
NODE_MIN_MAJOR = 22
STATIC_UNFETCHED = "not fetched yet (downloads about 70 MB on first use)"

FfmpegSource = Literal["system", "static", "static-unfetched", "none"]

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
    mem0_key: bool = False


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
        paths = media.ffmpeg_paths(allow_fetch=False)
        return media.ffmpeg_version(paths[0]), "static"
    if importlib.util.find_spec("static_ffmpeg") is not None:
        return None, "static-unfetched"
    return None, "none"


def _ytdlp_version() -> str | None:
    try:
        return importlib.metadata.version("yt-dlp")
    except importlib.metadata.PackageNotFoundError:
        return None


def probe_machine() -> Probe:
    """Look at the machine. No network, no installs; subprocess `--version` calls only."""
    ffmpeg, source = _probe_ffmpeg()
    node = _version_output("node")
    return Probe(
        uv=_second_token(_version_output("uv")),
        python=platform.python_version(),
        ffmpeg=ffmpeg,
        ffmpeg_source=source,
        ytdlp=_ytdlp_version(),
        node=node.lstrip("v") if node else None,
        deno=_second_token(_version_output("deno")),
        whisper_mlx=importlib.util.find_spec("mlx_whisper") is not None,
        whisper_faster=importlib.util.find_spec("faster_whisper") is not None,
        apple_silicon=sys.platform == "darwin" and platform.machine() == "arm64",
        cloud_keys=[key for key in CLOUD_KEYS if os.environ.get(key)],
        treg_on_path=shutil.which("treg") is not None,
        mem0_key=bool(os.environ.get("MEM0_API_KEY")),
    )


def _node_ok(version: str | None) -> bool:
    if not version:
        return False
    try:
        return int(version.split(".")[0]) >= NODE_MIN_MAJOR
    except ValueError:
        return False


def compute_tier(p: Probe) -> Tier:
    """Highest match, not a nested ladder: Tier 3 is Tier 1 plus treg (plan issue 10)."""
    whisper = p.whisper_mlx or p.whisper_faster
    if whisper and p.treg_on_path:
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


def _extra_command(plugin_root: str | None, extra: str) -> str:
    if plugin_root:
        return f'uv sync --project "{plugin_root}" --extra {extra}'
    return f'uv tool install "skipwatch[{extra}]"'


def ytdlp_upgrade_command(plugin_root: str | None) -> str:
    if plugin_root:
        return f'uv sync --project "{plugin_root}" --upgrade-package yt-dlp'
    return "uv tool upgrade skipwatch"


def _missing_for(tier: Tier | None, p: Probe, plugin_root: str | None) -> list[DoctorMissing]:
    if tier == "0":
        return [
            DoctorMissing(
                name="uv",
                unlocks=TIER_REASON["0"],
                install_command="install uv from https://docs.astral.sh/uv/",
            )
        ]
    if tier == "1":
        extra = "mlx" if p.apple_silicon else "whisper"
        return [
            DoctorMissing(
                name="whisper",
                unlocks=TIER_REASON["1"],
                install_command=_extra_command(plugin_root, extra),
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


def _warnings(p: Probe, today: date, plugin_root: str | None) -> list[str]:
    warnings: list[str] = []
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
        warnings.append(f"ffmpeg not found; run: {_sync_command(plugin_root)}")
    return warnings


def _sync_command(plugin_root: str | None) -> str:
    return f'uv sync --project "{plugin_root}"' if plugin_root else "uv tool install skipwatch"


def _ffmpeg_detail(p: Probe) -> str:
    if p.ffmpeg_source == "static-unfetched":
        return f"static ffmpeg: {STATIC_UNFETCHED}"
    return p.ffmpeg_source


def _components(p: Probe) -> list[DoctorComponent]:
    return [
        DoctorComponent(name="uv", found=p.uv is not None, version=p.uv),
        DoctorComponent(name="python", found=True, version=p.python),
        DoctorComponent(
            name="ffmpeg",
            found=p.ffmpeg_source in ("system", "static"),
            version=p.ffmpeg,
            detail=_ffmpeg_detail(p),
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
        DoctorComponent(name="apple-silicon", found=p.apple_silicon),
        DoctorComponent(
            name="cloud-keys", found=bool(p.cloud_keys), detail=", ".join(p.cloud_keys)
        ),
        DoctorComponent(
            name="treg",
            found=p.treg_on_path,
            detail="on PATH, login not verified" if p.treg_on_path else "",
        ),
        DoctorComponent(name="mem0-key", found=p.mem0_key),
    ]


def build_report(p: Probe, today: date, plugin_root: str | None) -> DoctorReport:
    tier = compute_tier(p)
    next_tier = NEXT_TIER[tier]
    return DoctorReport(
        tier=tier,
        next_tier=next_tier,
        components=_components(p),
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
        lines.append(f"  {c.name}: {state}" + (f" ({c.detail})" if c.detail else ""))
    for m in r.missing:
        lines.append(f"Missing for Tier {r.next_tier}: {m.name}: {m.install_command}")
    lines.extend(f"Warning: {w}" for w in r.warnings)
    if any(c.name == "treg" and c.found for c in r.components):
        lines.append("treg: on PATH, login not verified")
    return lines
