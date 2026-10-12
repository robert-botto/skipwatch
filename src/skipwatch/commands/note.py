"""note: record a degradation or unread frames in <work>/degradations.json.

`review` reads the file, so a resumed run keeps what an earlier session recorded
(skill audit 4 fix 2). Repeats are skipped; order is kept.
"""

from pathlib import Path
from typing import Annotated

import typer

from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.output import progress
from skipwatch.review import DEGRADATIONS_FILE, read_degradations
from skipwatch.runner import run_command
from skipwatch.workdir import write_model


def _value(degradation: str | None, unread: str | None) -> tuple[str, str]:
    if (degradation is None) == (unread is None):
        raise SkipwatchError(ExitCode.USAGE, "give exactly one of --degradation and --unread")
    field, value = ("degradations", degradation) if unread is None else ("unread", unread)
    assert value is not None
    if not value.strip() or "\n" in value or "\r" in value:
        raise SkipwatchError(ExitCode.USAGE, "the value must be one non-empty line")
    return field, value


def _note(work: Path, degradation: str | None, unread: str | None) -> int:
    field, value = _value(degradation, unread)
    if not (work / "stages.json").is_file():
        raise SkipwatchError(ExitCode.UNSUPPORTED_SOURCE, f"{work} is not a SkipWatch work folder")
    recorded = read_degradations(work)
    items: list[str] = getattr(recorded, field)
    if value not in items:
        items.append(value)
        write_model(work / DEGRADATIONS_FILE, recorded)
    progress(f"Noted: {value}")
    return 0


def register(app: typer.Typer) -> None:
    @app.command("note")
    def _cmd(
        work: Annotated[Path, typer.Option("--work", help="The run's work folder.")],
        degradation: Annotated[
            str | None, typer.Option("--degradation", help="A degradation line to record.")
        ] = None,
        unread: Annotated[
            str | None,
            typer.Option("--unread", help='Unread frames, as "<ids> (<reason>)".'),
        ] = None,
    ):
        """Record a degradation or unread frames for the review screen (kept for resume)."""
        run_command(lambda: _note(work, degradation, unread))
