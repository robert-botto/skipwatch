"""Where a run stopped (R-WORK-1, plan issue 5): the first stage that is not done.

A stage left `running` by a killed process counts as incomplete. Read-only: nothing here
writes to the work folder.
"""

import re
from pathlib import Path

from pydantic import ValidationError

from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import IngestBundle, ResumeResult, RunFile, StageName, StagesFile
from skipwatch.workdir import STAGE_ORDER, WorkDir, read_model

# work folders are named <slug>-<yyyymmdd-hhmmss> (workdir.new_work_path)
_STAMP_RE = re.compile(r"-(\d{8}-\d{6})$")


def _stages(work: Path) -> StagesFile:
    try:
        return read_model(work / "stages.json", StagesFile)
    except (OSError, ValidationError) as exc:
        raise SkipwatchError(
            ExitCode.UNSUPPORTED_SOURCE, f"{work} is not a SkipWatch work folder"
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


def resume_info(work: Path) -> ResumeResult:
    stages = _stages(work).stages
    completed: list[StageName] = [
        s for s in STAGE_ORDER if s in stages and stages[s].status == "done"
    ]
    return ResumeResult(
        work=str(work),
        next_stage=WorkDir(work).first_incomplete(),
        completed=completed,
        run=_run(work),
        media_present=_media_present(work),
    )


def _resumable(work: Path) -> bool:
    try:
        stages = read_model(work / "stages.json", StagesFile).stages
    except (OSError, ValidationError):
        return False
    review = stages.get("review")
    if review is not None and review.status == "done":
        return False
    return WorkDir(work).first_incomplete() is not None


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
