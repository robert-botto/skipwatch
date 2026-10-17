"""Where a run stopped (R-WORK-1, plan issue 5): the first stage that is not done.

A stage left `running` by a killed process counts as incomplete. Read-only: nothing here
writes to the work folder.
"""

import re
from pathlib import Path

from pydantic import ValidationError

from skipwatch.checks.frontmatter import is_skill_name
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import IngestBundle, ResumeResult, RunFile, StageName, StagesFile
from skipwatch.workdir import STAGE_ORDER, read_model

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


def skill_name(work: Path, run: RunFile | None) -> str | None:
    """The run's skill and staging folder: run.json's name when set (rename-staging writes
    it), else the one real folder under <W>/staging; None when that is not clear. A name
    that breaks the skill-name rule is ignored, never printed (REV8)."""
    if run is not None and run.name and is_skill_name(run.name):
        return run.name
    staging = work / "staging"
    if staging.is_symlink() or not staging.is_dir():
        return None
    folders = [p for p in staging.iterdir() if p.is_dir() or p.is_symlink()]
    if len(folders) != 1 or folders[0].is_symlink() or not is_skill_name(folders[0].name):
        return None
    return folders[0].name


def _media_present(work: Path) -> bool:
    try:
        bundle = read_model(work / "ingest.json", IngestBundle)
    except (OSError, ValidationError):
        return False
    if bundle.media is None:
        return False
    path = Path(bundle.media.path)
    return (path if path.is_absolute() else work / path).is_file()


# a text bundle has no media: these stages never run for it (run-protocol stage 3)
VIDEO_STAGES: tuple[StageName, ...] = ("transcribe", "frames", "plan", "read")


def _is_text(work: Path) -> bool:
    try:
        return read_model(work / "ingest.json", IngestBundle).source.kind == "text"
    except (OSError, ValidationError):
        return False


def next_stage(work: Path) -> StageName | None:
    """The first stage not done, or None once install is done: export is never resumed,
    since a missed export is covered by `/skipwatch export` (M6-R8). A text source skips
    the video stages, which never run for it."""
    stages = _stages(work).stages
    install = stages.get("install")
    if install is not None and install.status == "done":
        return None
    skip: tuple[StageName, ...] = VIDEO_STAGES if _is_text(work) else ()
    for name in STAGE_ORDER:
        if name not in skip and (name not in stages or stages[name].status != "done"):
            return name
    return None


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
