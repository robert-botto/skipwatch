import json
from pathlib import Path
from typing import Annotated

import typer

from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.review import ReviewInputs, screen
from skipwatch.runner import run_command

TEST_RUN = "Test run: "


def _review(
    work: Path,
    skill: Path,
    degradations: list[str],
    unread: list[str],
    test_run: str | None,
    json_out: bool,
) -> int:
    if test_run is not None and not test_run.startswith(TEST_RUN):
        raise SkipwatchError(
            ExitCode.USAGE, f"--test-run takes the line validate-test printed ({TEST_RUN}...)"
        )
    inputs = ReviewInputs(degradations=degradations, unread=unread, test_run=test_run)
    text = screen(work, skill, inputs)
    typer.echo(json.dumps({"screen": text}) if json_out else text, nl=json_out)
    return 0


def register(app: typer.Typer) -> None:
    @app.command("review")
    def _cmd(
        work: Annotated[Path, typer.Option("--work", help="The run's work folder.")],
        skill: Annotated[Path, typer.Option("--skill", help="The staged skill folder.")],
        degradation: Annotated[
            list[str] | None,
            typer.Option("--degradation", help="A recorded degradation (repeatable)."),
        ] = None,
        unread: Annotated[
            list[str] | None,
            typer.Option("--unread", help='Unread frames, as "<ids> (<reason>)" (repeatable).'),
        ] = None,
        test_run: Annotated[
            str | None,
            typer.Option("--test-run", help="The Test run: line validate-test printed."),
        ] = None,
        json_out: bool = typer.Option(False, "--json", help='Print {"screen": <text>}.'),
    ):
        """Print the review screen (without the prompt line) from the run's files."""
        run_command(
            lambda: _review(work, skill, degradation or [], unread or [], test_run, json_out)
        )
