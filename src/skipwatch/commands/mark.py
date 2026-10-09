"""mark: record the stages that run in the Claude session (read, distill, critique, review).

Engine stages mark themselves through run_stage; these four have no engine command, so the
orchestrator marks them here and stages.json carries their timings for resume (R-WORK-1).

merge-notes also lives here, as the read stage's other helper: when a reader skipped some
frames, only those frames are read again, into notes/batch-NN.retry.json, and this folds
them into the batch's notes file (section 15).
"""

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import BatchesFile, NotesFile
from skipwatch.output import progress
from skipwatch.runner import run_command
from skipwatch.workdir import WorkDir, read_model, write_model


class ClaudeStage(StrEnum):
    read = "read"
    distill = "distill"
    critique = "critique"
    review = "review"


class MarkStatus(StrEnum):
    running = "running"
    done = "done"
    failed = "failed"


def _mark(work_dir: Path, stage: ClaudeStage, status: MarkStatus) -> int:
    work = WorkDir(work_dir)
    if not work.file("stages.json").is_file():
        # never create a work folder here; a typo in the path must not start a new run
        raise SkipwatchError(
            ExitCode.UNSUPPORTED_SOURCE, f"{work_dir} is not a SkipWatch work folder"
        )
    work.mark(stage.value, status.value)
    progress(f"Marked {stage.value} {status.value}")
    return 0


def _read_notes(path: Path, batch: int) -> NotesFile:
    try:
        notes = read_model(path, NotesFile)
    except (OSError, ValidationError, ValueError) as exc:
        raise SkipwatchError(
            ExitCode.NO_CONTENT, f"cannot merge: {path.name} is missing or invalid"
        ) from exc
    if notes.batch != batch:
        raise SkipwatchError(
            ExitCode.NO_CONTENT, f"cannot merge: {path.name} is for batch {notes.batch}"
        )
    return notes


def _merge_notes(work_dir: Path, batch_id: int) -> int:
    batches_path = work_dir / "batches.json"
    if not batches_path.is_file():
        raise SkipwatchError(ExitCode.NO_CONTENT, f"{batches_path} not found; run plan first")
    batches = read_model(batches_path, BatchesFile).batches
    batch = next((b for b in batches if b.id == batch_id), None)
    if batch is None:
        raise SkipwatchError(ExitCode.NO_CONTENT, f"no batch {batch_id} in batches.json")
    main_path = work_dir / batch.notes_path
    retry_path = main_path.with_name(main_path.stem + ".retry.json")
    retry = _read_notes(retry_path, batch_id)
    main = _read_notes(main_path, batch_id)
    # the first reader's entries win; the retry only fills frames it left out
    by_id = {f.id: f for f in retry.frames} | {f.id: f for f in main.frames}
    frames = [by_id[i] for i in batch.frame_ids if i in by_id]
    added = len(frames) - sum(1 for f in main.frames if f.id in batch.frame_ids)
    write_model(main_path, NotesFile(batch=batch_id, frames=frames))
    retry_path.unlink()
    missing = [i for i in batch.frame_ids if i not in by_id]
    tail = f"; still missing {', '.join(missing)}" if missing else ""
    progress(f"batch {batch_id}: merged {added} frame(s){tail}")
    return 0


def register(app: typer.Typer) -> None:
    @app.command("mark")
    def _cmd(
        work: Annotated[Path, typer.Option("--work", help="The run's work folder.")],
        stage: Annotated[ClaudeStage, typer.Option("--stage", help="A stage run by Claude.")],
        status: Annotated[MarkStatus, typer.Option("--status", help="The stage's new status.")],
    ):
        """Record the status of a stage that runs in the Claude session."""
        run_command(lambda: _mark(work, stage, status))

    @app.command("merge-notes")
    def _merge_cmd(
        work: Annotated[Path, typer.Option("--work", help="The run's work folder.")],
        batch: Annotated[int, typer.Option("--batch", help="The batch id to merge.")],
    ):
        """Fold notes/batch-NN.retry.json into the batch's notes file, in batch order."""
        run_command(lambda: _merge_notes(work, batch))
