"""Where a run stopped (R-WORK-1, plan issue 5): the first stage that is not done.

A stage left `running` by a killed process counts as incomplete. Read-only: nothing here
writes to the work folder.
"""

import importlib.util
import re
from pathlib import Path

from pydantic import ValidationError

from skipwatch.config import load_config
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import IngestBundle, ResumeResult, RunFile, StageName, StagesFile
from skipwatch.workdir import STAGE_ORDER, WorkDir, read_model

# work folders are named <slug>-<yyyymmdd-hhmmss> (workdir.new_work_path)
_STAMP_RE = re.compile(r"-(\d{8}-\d{6})$")


def _stages(work: Path) -> StagesFile:
    """Exit 2 when there is no stages.json; exit 7 when it is there but will not read (6)."""
    path = work / "stages.json"
    if not path.is_file():
        raise SkipwatchError(ExitCode.UNSUPPORTED_SOURCE, f"{work} is not a SkipWatch work folder")
    try:
        return read_model(path, StagesFile)
    except (OSError, ValidationError) as exc:
        detail = exc.strerror if isinstance(exc, OSError) else f"{exc.error_count()} error(s)"
        raise SkipwatchError(
            ExitCode.NO_CONTENT, f"stages.json is unreadable: {path}: {detail or exc}"
        ) from exc


def _run(work: Path) -> RunFile | None:
    try:
        return read_model(work / "run.json", RunFile)
    except (OSError, ValidationError):
        return None  # written by the orchestrator; resume still names the stage without it


def _media_present(work: Path) -> bool:
    try:
        bundle = read_model(work / "ingest.json", IngestBundle)
    except (OSError, ValidationError):
        return False
    if bundle.media is None:
        return False
    path = Path(bundle.media.path)
    return (path if path.is_absolute() else work / path).is_file()


def _export_command_exists() -> bool:
    return importlib.util.find_spec("skipwatch.commands.export") is not None


def _exports_enabled() -> bool:
    """M6 seam: export is a stage to resume only once its command exists and is enabled."""
    if not _export_command_exists():
        return False
    try:
        exports = load_config().exports
    except (OSError, ValueError):
        return False
    return exports.mem0.enabled or exports.notes.enabled


def next_stage(work: Path) -> StageName | None:
    """The first stage not done; a run whose only missing stage is export is complete
    unless exports are on, since export never runs before M6."""
    stage = WorkDir(work).first_incomplete()
    if stage == "export" and not _exports_enabled():
        return None
    return stage


def resume_info(work: Path) -> ResumeResult:
    stages = _stages(work).stages
    completed: list[StageName] = [
        s for s in STAGE_ORDER if s in stages and stages[s].status == "done"
    ]
    return ResumeResult(
        work=str(work),
        next_stage=next_stage(work),
        completed=completed,
        run=_run(work),
        media_present=_media_present(work),
    )


def _resumable(work: Path) -> bool:
    # without run.json there is nothing to repeat: a folder abandoned right after new-work
    if _run(work) is None:
        return False
    try:
        stages = read_model(work / "stages.json", StagesFile).stages
    except (OSError, ValidationError):
        return False
    review = stages.get("review")
    if review is not None and review.status == "done":
        return False
    return next_stage(work) is not None


def newest_incomplete(home: Path) -> Path | None:
    """The newest work folder (by its timestamp suffix) that is unfinished and not reviewed."""
    root = home / "work"
    if not root.is_dir():
        return None
    stamped = []
    for folder in root.iterdir():
        match = _STAMP_RE.search(folder.name)
        if match and folder.is_dir():
            stamped.append((match.group(1), folder.name, folder))
    for _, _, folder in sorted(stamped, reverse=True):
        if _resumable(folder):
            return folder
    return None
