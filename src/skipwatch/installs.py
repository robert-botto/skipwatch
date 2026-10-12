"""$SKIPWATCH_HOME/installs.json: where SkipWatch installed skills (M5-M6 issue 10).

`list` scans the three scope folders, but a skill installed with --to lives anywhere; this log
is how `list` finds it. The log is a convenience: a missing or broken file reads as empty.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from skipwatch.config import skipwatch_home
from skipwatch.models import InstallRecord, InstallResult, InstallsFile
from skipwatch.output import progress
from skipwatch.workdir import read_model, write_model

INSTALLS = "installs.json"


def load() -> InstallsFile:
    path = skipwatch_home() / INSTALLS
    if not path.exists():
        return InstallsFile()
    try:
        return read_model(path, InstallsFile)
    except (OSError, ValidationError, ValueError) as exc:
        progress(f"ignoring {path}: {exc.__class__.__name__}")
        return InstallsFile()


def resolved(path: str) -> Path | None:
    """A logged path resolved, or None when it cannot be (a NUL byte, a broken file system)."""
    try:
        return Path(path).resolve()
    except (OSError, ValueError):
        return None


def record(
    result: InstallResult, origin: Literal["run", "pack"], now: datetime | None = None
) -> None:
    """Log an install, replacing any record for the same resolved folder."""
    path = Path(result.path).resolve()
    stamp = (now or datetime.now(UTC)).astimezone(UTC)
    entry = InstallRecord(
        name=result.name,
        path=str(path),
        scope=result.scope,
        origin=origin,
        installed_at=stamp.isoformat(timespec="seconds").replace("+00:00", "Z"),
    )
    log = load()
    # a record whose path cannot be resolved is kept as is; it can never match this one
    kept = [r for r in log.installs if resolved(r.path) != path]
    home = skipwatch_home()
    home.mkdir(parents=True, exist_ok=True)
    write_model(home / INSTALLS, InstallsFile(installs=[*kept, entry]))
