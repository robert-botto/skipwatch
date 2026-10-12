"""Work-folder housekeeping the skill used to run as shell (skill audit 4 fix 1).

Each command touches only paths inside the one work folder it is given, so the skill's
allowed-tools need no `cp -R` or `rm -rf`.
"""

import shutil
from pathlib import Path
from typing import Annotated

import typer

from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.output import progress
from skipwatch.runner import run_command


def _work_folder(work: Path) -> Path:
    """The work folder, resolved; never a path that only looks like one (exit 2, as mark)."""
    if not (work / "stages.json").is_file():
        raise SkipwatchError(ExitCode.UNSUPPORTED_SOURCE, f"{work} is not a SkipWatch work folder")
    return work.resolve()


def _remove(path: Path) -> None:
    """Delete a file or folder; a symlink is unlinked, never followed."""
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _snapshot_draft(work: Path) -> int:
    work = _work_folder(work)
    draft = work / "draft"
    if not draft.is_dir() or draft.is_symlink():
        raise SkipwatchError(ExitCode.NO_CONTENT, f"no draft to snapshot: {draft}")
    snapshot = work / "draft-pre-critic"
    _remove(snapshot)
    shutil.copytree(draft, snapshot, symlinks=True)
    progress(f"Snapshot: {snapshot}")
    return 0


def register(app: typer.Typer) -> None:
    @app.command("snapshot-draft")
    def _snapshot_cmd(
        work: Annotated[Path, typer.Option("--work", help="The run's work folder.")],
    ):
        """Replace <work>/draft-pre-critic with a copy of <work>/draft (stage 7 step 1)."""
        run_command(lambda: _snapshot_draft(work))
