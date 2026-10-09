"""validate-notes: check frame-reader output before the orchestrator reads it (section 15).

A notes file must parse as skipwatch/notes/1, carry its batch id and cover exactly its batch's
frames, so a reader that wrote the wrong batch is caught and re-dispatched.
"""

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import Batch, BatchesFile, NotesFile
from skipwatch.output import progress
from skipwatch.runner import run_command
from skipwatch.workdir import read_model


def batch_problem(work: Path, batch: Batch) -> str | None:
    """One line describing what is wrong with this batch's notes file, or None when valid."""
    path = work / batch.notes_path
    if not path.is_file():
        return f"missing {batch.notes_path}"
    try:
        notes = read_model(path, NotesFile)
    except (ValidationError, ValueError) as exc:
        return f"invalid {batch.notes_path} ({type(exc).__name__})"
    if notes.batch != batch.id:
        return f"batch id is {notes.batch}, expected {batch.id}"
    got, want = {f.id for f in notes.frames}, set(batch.frame_ids)
    if got != want:
        parts = []
        if want - got:
            parts.append("missing " + ", ".join(sorted(want - got)))
        if got - want:
            parts.append("unexpected " + ", ".join(sorted(got - want)))
        return "frames " + "; ".join(parts)
    return None


def _validate_notes(work: Path) -> int:
    batches_path = work / "batches.json"
    if not batches_path.is_file():
        raise SkipwatchError(ExitCode.NO_CONTENT, f"{batches_path} not found; run plan first")
    batches = read_model(batches_path, BatchesFile).batches
    bad = 0
    for batch in batches:
        problem = batch_problem(work, batch)
        if problem:
            bad += 1
            progress(f"batch {batch.id}: {problem}")
    if bad:
        return int(ExitCode.CHECK_FAILED)
    progress(f"{len(batches)} notes files valid")
    return 0


def register(app: typer.Typer) -> None:
    @app.command("validate-notes")
    def _cmd(
        work: Annotated[Path, typer.Option("--work", help="The run's work folder.")],
    ):
        """Check every notes file against batches.json. Exit 1 lists the bad batches."""
        run_command(lambda: _validate_notes(work))
