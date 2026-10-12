"""Work-folder housekeeping the skill used to run as shell (skill audit 4 fix 1).

Each command touches only paths inside the one work folder it is given, so the skill's
allowed-tools need no `cp -R` or `rm -rf`.
"""

import os
import shutil
from pathlib import Path
from typing import Annotated

import typer

from skipwatch.config import skipwatch_home
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.output import progress
from skipwatch.runner import run_command
from skipwatch.workdir import STAGE_ORDER, WorkDir


def home_work_folder(work: Path) -> Path:
    """The work folder, resolved: directly under the home's work/ (as --home sets it), not a
    symlink, with a stages.json that reads. Anything else is exit 64 before any deletion."""
    return _home_folder(work, "work")


def home_work_or_pack_folder(work: Path, require_stages: bool = True) -> Path:
    """home_work_folder, or the same rule for the home's packs/ (a pack test run's folder).
    When neither fits, the work/ refusal is the one raised. require_stages=False checks the
    place only (resume reports a missing stages.json with its own exit code)."""
    try:
        return _home_folder(work, "work", require_stages)
    except SkipwatchError as work_error:
        try:
            return _home_folder(work, "packs", require_stages)
        except SkipwatchError:
            raise work_error from None


def _home_folder(work: Path, area: str, require_stages: bool = True) -> Path:
    """home_work_folder's rule for the home's work/ or packs/ folder."""
    root = (skipwatch_home() / area).resolve()
    resolved = work.resolve()
    if work.is_symlink() or resolved.parent != root or ".." in work.parts:
        raise SkipwatchError(ExitCode.USAGE, f"{work} is not a work folder directly under {root}")
    if not require_stages:
        return resolved
    try:
        WorkDir(resolved).stages()
    except (OSError, ValueError) as exc:
        raise SkipwatchError(ExitCode.USAGE, f"{work} has no readable stages.json") from exc
    return resolved


def _refuse_dotdot(path: Path, flag: str) -> None:
    if ".." in path.parts:
        raise SkipwatchError(ExitCode.USAGE, f"{flag} {path} must not contain ..")


def path_under(work: Path, sub: str, path: Path, flag: str) -> Path:
    """path resolved, refused (exit 64) unless it lies inside <work>/<sub> with no `..` and no
    symlink anywhere inside that folder, the last component included (adversarial review REV6).
    work is an already-checked folder; path itself need not exist yet."""
    folder = work / sub

    def refuse(why: str) -> SkipwatchError:
        return SkipwatchError(ExitCode.USAGE, f"{flag} {path} {why}")

    _refuse_dotdot(path, flag)
    if folder.is_symlink():
        raise refuse(f"is in {folder}, which is a symlink")
    resolved = path.resolve()
    if not resolved.is_relative_to(folder) or resolved == folder:
        raise refuse(f"is not inside {folder}")
    given = Path(os.path.abspath(path))
    for part in (given, *given.parents):
        if not os.path.lexists(part):
            continue
        if not part.resolve().is_relative_to(folder):
            break
        if part.is_symlink():
            raise refuse(f"goes through a symlink: {part}")
    return resolved


def log_path(log: Path) -> Path:
    """--log resolved, refused (exit 64) unless it lies under <W>/logs of a work or pack folder
    W as home_work_or_pack_folder checks it, with no `..` and no symlink inside logs/."""
    _refuse_dotdot(log, "--log")
    resolved = log.resolve()
    for area in ("work", "packs"):
        root = (skipwatch_home() / area).resolve()
        if not resolved.is_relative_to(root):
            continue
        parts = resolved.relative_to(root).parts
        if len(parts) >= 2:
            work = _home_folder(root / parts[0], area)
            return path_under(work, "logs", log, "--log")
    raise SkipwatchError(
        ExitCode.USAGE, f"--log {log} is not inside the logs/ folder of a work folder"
    )


def remove_path(path: Path) -> None:
    """Delete a file or folder; a symlink is unlinked, never followed."""
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


# what stage 10 cleanup deletes after an install, besides media: the drafts and the raw text
# a secret said aloud or posted could sit in (the 7-day run cache keeps its own copies)
DRAFT_PATHS = (
    "draft",
    "draft-pre-critic",
    "test-run",
    "notes",
    "frames",
    "outline.md",
    "critique.json",
    "transcript.json",
    "ingest.json",
    "logs/probe.json",
)
KEEP_DRAFTS = "SKIPWATCH_KEEP_DRAFTS"
SCRATCH_PREFIX = "test-run-"


def _inside(work: Path, path: Path) -> bool:
    """Whether path's folder resolves inside work, so deleting path cannot reach outside."""
    return path.parent.resolve().is_relative_to(work)


def _scratch_folder(work: Path, scratch: Path) -> Path:
    """--scratch resolved: this project's <cwd>/.skipwatch/test-run-<name> only. Never a
    symlink, never another project's folder, never one holding the work folder."""
    resolved = scratch.resolve()
    tester = (
        resolved.parent == Path.cwd().resolve() / ".skipwatch"
        and resolved.name.startswith(SCRATCH_PREFIX)
        and len(resolved.name) > len(SCRATCH_PREFIX)
    )
    if tester and not scratch.is_symlink() and not work.is_relative_to(resolved):
        return resolved
    raise SkipwatchError(
        ExitCode.USAGE,
        f"--scratch must be ./.skipwatch/{SCRATCH_PREFIX}<name> in this project and not a "
        f"symlink, not {scratch}",
    )


def _cleanup(work: Path, keep_media: bool, scratch: Path | None) -> int:
    work = home_work_folder(work)
    scratch = None if scratch is None else _scratch_folder(work, scratch)
    targets = [] if keep_media else [work / "media"]
    if os.environ.get(KEEP_DRAFTS) != "1":
        targets += [work / name for name in DRAFT_PATHS]
        if scratch is not None:
            targets.append(scratch)
    removed = 0
    for path in targets:
        if path != scratch and not _inside(work, path):
            continue
        if path.is_symlink() or path.exists():
            remove_path(path)
            removed += 1
    progress(f"Cleanup: removed {removed} item(s) from {work}")
    return 0


def _discard_work(work: Path) -> int:
    """Remove a work folder new-work just made (run-fallbacks.md), and nothing else."""
    root = (skipwatch_home() / "work").resolve()
    resolved = work.resolve()

    def refuse(why: str) -> SkipwatchError:
        return SkipwatchError(ExitCode.USAGE, f"will not discard {work}: {why}")

    if work.is_symlink() or resolved.parent != root:
        raise refuse(f"not a work folder directly under {root}")
    try:
        stages = WorkDir(resolved).stages().stages
    except (OSError, ValueError) as exc:
        raise refuse("no readable stages.json") from exc
    started = [s for s in STAGE_ORDER[1:] if s in stages and stages[s].status == "done"]
    if started:
        raise refuse(f"stage {started[0]} is done")
    shutil.rmtree(resolved)
    progress(f"Discarded {resolved}")
    return 0


def _discard_pack(work: Path, scratch: Path | None) -> int:
    """Remove a pack work folder unpack made, after install or cancel (sharing.md), and this
    project's test-run scratch folder; every path is checked before anything is deleted."""
    work = _home_folder(work, "packs")
    scratch = None if scratch is None else _scratch_folder(work, scratch)
    shutil.rmtree(work)
    if scratch is not None and scratch.exists():
        shutil.rmtree(scratch)
    progress(f"Discarded {work}")
    return 0


def _snapshot_draft(work: Path) -> int:
    work = home_work_folder(work)
    draft = work / "draft"
    if not draft.is_dir() or draft.is_symlink():
        raise SkipwatchError(ExitCode.NO_CONTENT, f"no draft to snapshot: {draft}")
    snapshot = work / "draft-pre-critic"
    remove_path(snapshot)
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

    @app.command("cleanup")
    def _cleanup_cmd(
        work: Annotated[Path, typer.Option("--work", help="The run's work folder.")],
        keep_media: bool = typer.Option(False, "--keep-media", help="Keep <work>/media."),
        scratch: Annotated[
            Path | None,
            typer.Option("--scratch", help="The tester's <project>/.skipwatch/test-run-<name>."),
        ] = None,
    ):
        """Delete a finished run's media, drafts and raw text; keep its record for resume.

        SKIPWATCH_KEEP_DRAFTS=1 keeps everything but the media.
        """
        run_command(lambda: _cleanup(work, keep_media, scratch))

    @app.command("discard-work")
    def _discard_cmd(
        work: Annotated[Path, typer.Option("--work", help="The work folder new-work printed.")],
    ):
        """Remove a fresh work folder under the home's work/ (only the first stage done)."""
        run_command(lambda: _discard_work(work))

    @app.command("discard-pack")
    def _discard_pack_cmd(
        work: Annotated[Path, typer.Option("--work", help="The pack work folder unpack printed.")],
        scratch: Annotated[
            Path | None,
            typer.Option("--scratch", help="The tester's <project>/.skipwatch/test-run-<name>."),
        ] = None,
    ):
        """Remove a pack work folder under the home's packs/, and the test run's scratch."""
        run_command(lambda: _discard_pack(work, scratch))
