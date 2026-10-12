"""note: record a degradation or unread frames in <work>/degradations.json.

`review` reads the file, so a resumed run keeps what an earlier session recorded
(skill audit 4 fix 2). Repeats are skipped; order is kept.
"""

import unicodedata
from pathlib import Path
from typing import Annotated

import typer

from skipwatch.commands.workfiles import home_work_folder, remove_path
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.output import progress
from skipwatch.review import DEGRADATIONS_FILE, read_degradations
from skipwatch.runner import run_command
from skipwatch.workdir import write_model


def _unprintable(char: str) -> bool:
    category = unicodedata.category(char)
    return category[0] == "C" or category in ("Zl", "Zp")


CRITIC_FAILED = "critic failed twice"


def _value(degradation: str | None, unread: str | None, critic_failed: bool) -> tuple[str, str]:
    given = [degradation is not None, unread is not None, critic_failed]
    if given.count(True) != 1:
        raise SkipwatchError(
            ExitCode.USAGE, "give exactly one of --degradation, --unread and --critic-failed"
        )
    if critic_failed:
        return "degradations", CRITIC_FAILED
    field, value = ("degradations", degradation) if unread is None else ("unread", unread)
    assert value is not None
    # control, format, surrogate, private-use and unassigned characters (category C*) and
    # line or paragraph separators (Zl, Zp) could reshape the review screen it is printed on
    if not value.strip() or any(_unprintable(c) for c in value):
        raise SkipwatchError(
            ExitCode.USAGE, "the value must be one non-empty line of printable text"
        )
    return field, value


def _note(work: Path, degradation: str | None, unread: str | None, critic_failed: bool) -> int:
    field, value = _value(degradation, unread, critic_failed)
    work = home_work_folder(work)
    recorded = read_degradations(work)
    items: list[str] = getattr(recorded, field)
    if value not in items:
        items.append(value)
        write_model(work / DEGRADATIONS_FILE, recorded)
    if critic_failed:
        # stage 7 continues without the critic, so a half-written critique must not be read
        remove_path(work / "critique.json")
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
        critic_failed: bool = typer.Option(
            False,
            "--critic-failed",
            help=f'Record "{CRITIC_FAILED}" and delete <work>/critique.json.',
        ),
    ):
        """Record a degradation or unread frames for the review screen (kept for resume)."""
        run_command(lambda: _note(work, degradation, unread, critic_failed))
