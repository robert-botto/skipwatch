"""validate-notes: check frame-reader output before the orchestrator reads it (section 15).

A notes file must parse as skipwatch/notes/1, carry its batch id and cover exactly its batch's
frames, so a reader that wrote the wrong batch is caught and re-dispatched.
"""

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from skipwatch.commands.workfiles import home_work_or_pack_folder
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import Batch, BatchesFile, NotesError, NotesFile, ValidateNotesResult
from skipwatch.output import emit_json, progress
from skipwatch.runner import run_command
from skipwatch.workdir import read_model


def field_path(loc: tuple[int | str, ...]) -> str | None:
    """A ValidationError location as a dotted path ("frames.0.t"); None for the whole file."""
    return ".".join(str(part) for part in loc) or None


def batch_errors(work: Path, batch: Batch) -> list[NotesError]:
    """Everything wrong with this batch's notes file; empty when valid."""
    path = work / batch.notes_path
    if not path.is_file():
        return [NotesError(batch=batch.id, message=f"missing {batch.notes_path}")]
    try:
        notes = read_model(path, NotesFile)
    except ValidationError as exc:
        return [
            NotesError(
                batch=batch.id,
                field=field_path(err["loc"]),
                message=f"invalid {batch.notes_path} ({err['msg']})",
            )
            for err in exc.errors()
        ]
    except ValueError as exc:
        return [
            NotesError(batch=batch.id, message=f"invalid {batch.notes_path} ({type(exc).__name__})")
        ]
    if notes.batch != batch.id:
        return [
            NotesError(
                batch=batch.id,
                field="batch",
                message=f"batch id is {notes.batch}, expected {batch.id}",
            )
        ]
    got, want = {f.id for f in notes.frames}, set(batch.frame_ids)
    return [NotesError(batch=batch.id, frame=f, message="missing") for f in sorted(want - got)] + [
        NotesError(batch=batch.id, frame=f, message="unexpected") for f in sorted(got - want)
    ]


def batch_problem(errors: list[NotesError]) -> str:
    """One human line for a bad batch's errors, in the shapes run-protocol.md routes on."""
    if errors[0].frame is None:
        return errors[0].message
    parts = []
    for kind in ("missing", "unexpected"):
        ids = [e.frame for e in errors if e.message == kind and e.frame]
        if ids:
            parts.append(f"{kind} " + ", ".join(ids))
    return "frames " + "; ".join(parts)


def _validate_notes(work: Path, json_out: bool) -> int:
    work = home_work_or_pack_folder(work)
    batches_path = work / "batches.json"
    if not batches_path.is_file():
        raise SkipwatchError(ExitCode.NO_CONTENT, f"{batches_path} not found; run plan first")
    batches = read_model(batches_path, BatchesFile).batches
    errors: list[NotesError] = []
    for batch in batches:
        found = batch_errors(work, batch)
        if found:
            progress(f"batch {batch.id}: {batch_problem(found)}")
        errors += found
    if json_out:
        emit_json(ValidateNotesResult(ok=not errors, batches=len(batches), errors=errors))
    if errors:
        return int(ExitCode.CHECK_FAILED)
    progress(f"{len(batches)} notes files valid")
    return 0


def register(app: typer.Typer) -> None:
    @app.command("validate-notes")
    def _cmd(
        work: Annotated[Path, typer.Option("--work", help="The run's work folder.")],
        json_out: bool = typer.Option(False, "--json", help="Print the result as JSON."),
    ):
        """Check every notes file against batches.json. Exit 1 lists the bad batches."""
        run_command(lambda: _validate_notes(work, json_out))
