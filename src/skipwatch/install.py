"""Install a checked staging folder into a skills scope (R-SK-1, R-REV-2).

Install refuses drafts that `skipwatch check` has not passed, never replaces an existing skill
without --force, and with --force moves the old copy to $SKIPWATCH_HOME/backups/ before copying
anything. It never touches the work folder: media cleanup is the orchestrator's call.
"""

import os
import shutil
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from skipwatch import installs
from skipwatch.config import load_config, skipwatch_home
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.manifest import PACK_IGNORED_NAMES, finalize_manifest, pack_refusal
from skipwatch.models import CheckReport, IngestBundle, InstallResult
from skipwatch.output import progress
from skipwatch.workdir import read_model

Scope = Literal["user", "project", "agents"]
TargetScope = Literal["user", "project", "agents", "dir"]

UNCHECKED = "run skipwatch check first; install refuses unchecked drafts"
STALE = "staging changed since check; run skipwatch check again"


def target_dir(
    scope: Scope | None, to: Path | None, name: str, cwd: Path, home: Path
) -> tuple[Path, TargetScope]:
    """Where a skill named `name` goes. --to wins over --scope; no scope means user."""
    if to is not None:
        return to / name, "dir"
    if scope == "project":
        return cwd / ".claude" / "skills" / name, "project"
    if scope == "agents":
        return cwd / ".agents" / "skills" / name, "agents"
    return home / ".claude" / "skills" / name, "user"


def scope_target(scope: Scope | None, name: str, cwd: Path, home: Path) -> tuple[Path, TargetScope]:
    """Where a skill named `name` goes without --to: --scope, else config.toml [install] scope."""
    return target_dir(scope or load_config().install.scope, None, name, cwd, home)


def _walk(root: Path) -> Iterator[Path]:
    """root and everything under it, without following symlinks."""
    yield root
    for folder, dirs, files in os.walk(root):
        for entry in (*dirs, *files):
            yield Path(folder) / entry


def _require_passed_check(staging: Path) -> None:
    """The work folder's check report must pass for this skill and postdate every staged file."""
    path = staging.parent.parent / "check-report.json"
    try:
        report = read_model(path, CheckReport)
    except (OSError, ValidationError) as exc:
        raise SkipwatchError(ExitCode.CHECK_FAILED, UNCHECKED) from exc
    if not report.passed or report.skill != staging.name:
        raise SkipwatchError(ExitCode.CHECK_FAILED, UNCHECKED)
    checked_at = path.stat().st_mtime_ns
    if any(entry.lstat().st_mtime_ns > checked_at for entry in _walk(staging)):
        raise SkipwatchError(ExitCode.CHECK_FAILED, STALE)


def _ingest_pack(staging: Path) -> bool:
    """Whether unpack made this work folder and pack_refusal honours it; any error means no."""
    work = staging.parent.parent
    try:
        pack = read_model(work / "ingest.json", IngestBundle).pack
        return pack is not None and pack_refusal(staging, work, pack) is None
    except (OSError, ValidationError, ValueError, SkipwatchError):
        return False


def _backup_path(name: str, now: datetime) -> Path:
    base = skipwatch_home() / "backups" / f"{name}-{now:%Y%m%d-%H%M%S}"
    path, n = base, 1
    while path.exists() or path.is_symlink():
        path = base.with_name(f"{base.name}-{n}")
        n += 1
    return path


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def install_root(given: Path) -> Path:
    """--to resolved: never a symlink itself, never inside the home's work/ or packs/, where
    the engine's own guarded folders live (adversarial review REV6 item 4)."""
    if given.is_symlink():
        raise SkipwatchError(ExitCode.USAGE, f"--to {given} is a symlink")
    resolved = given.resolve()
    for area in ("work", "packs"):
        if resolved.is_relative_to((skipwatch_home() / area).resolve()):
            raise SkipwatchError(
                ExitCode.USAGE, f"--to {given} is inside the SkipWatch home's {area}/ folder"
            )
    return resolved


def install(
    staging: Path,
    scope: Scope | None,
    to: Path | None,
    force: bool,
    *,
    cwd: Path | None = None,
    home: Path | None = None,
    now: datetime | None = None,
) -> InstallResult:
    staging = staging.resolve()
    if not staging.is_dir():
        raise SkipwatchError(ExitCode.USAGE, f"{staging} is not a folder")
    name = staging.name
    _require_passed_check(staging)

    cwd = cwd or Path.cwd()
    home = home or Path.home()
    if to is not None:
        target, resolved = target_dir(scope, install_root(cwd / to), name, cwd, home)
    else:
        target, resolved = scope_target(scope, name, cwd, home)

    backup: Path | None = None
    if target.exists() or target.is_symlink():
        if not force:
            raise SkipwatchError(
                ExitCode.TARGET_EXISTS,
                f"{target} exists; pass --force to replace (a backup is made first)",
            )
        backup = _backup_path(name, now or datetime.now())
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(target, backup)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staging, target, ignore=shutil.ignore_patterns(*PACK_IGNORED_NAMES))
        finalize_manifest(target, checks_passed=True)
    except BaseException:
        _remove(target)
        if backup is not None:
            shutil.move(backup, target)
        raise

    result = InstallResult(
        name=name,
        path=str(target),
        scope=resolved,
        backup=str(backup) if backup is not None else None,
    )
    origin = "pack" if _ingest_pack(staging) else "run"
    try:
        installs.record(result, origin)
    except (OSError, ValueError) as exc:
        progress(f"could not record the install: {exc}")
    return result
