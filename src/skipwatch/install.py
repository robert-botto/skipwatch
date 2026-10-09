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

from skipwatch.config import load_config, skipwatch_home
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import CheckReport, InstallResult
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


def _backup_path(name: str, now: datetime) -> Path:
    base = skipwatch_home() / "backups" / f"{name}-{now:%Y%m%d-%H%M%S}"
    path, n = base, 1
    while path.exists() or path.is_symlink():
        path = base.with_name(f"{base.name}-{n}")
        n += 1
    return path


def _finalize(target: Path) -> None:
    # M1-D owns manifest.py; imported here so the rest of install works without it.
    from skipwatch.manifest import finalize_manifest  # pyright: ignore[reportMissingImports]

    finalize_manifest(target, checks_passed=True)


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


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

    if to is None and scope is None:
        scope = load_config().install.scope
    cwd = cwd or Path.cwd()
    if to is not None:
        to = (cwd / to).resolve()
    target, resolved = target_dir(scope, to, name, cwd, home or Path.home())

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
        shutil.copytree(staging, target)
        _finalize(target)
    except BaseException:
        _remove(target)
        if backup is not None:
            shutil.move(backup, target)
        raise

    return InstallResult(
        name=name,
        path=str(target),
        scope=resolved,
        backup=str(backup) if backup is not None else None,
    )
