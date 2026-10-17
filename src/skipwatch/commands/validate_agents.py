"""validate-critique and validate-test: check agent output before the orchestrator trusts it.

The skill-critic writes critique.json and the skill-tester writes test-report.json (8.6, 8.9).
Like validate-notes, these commands parse the file against its model so a malformed or
overreaching report is caught and the agent re-dispatched. The critic's own `score` is never
trusted: it is rewritten to the mean of the five rubric lines (M5-M6 issue 20).
"""

from pathlib import Path
from statistics import mean
from typing import Annotated, TypeVar, get_args

import typer
from pydantic import BaseModel, ValidationError

from skipwatch import skillmd
from skipwatch.commands.validate_notes import field_path
from skipwatch.commands.workfiles import home_work_or_pack_folder
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import Critique, TesterReport
from skipwatch.output import progress
from skipwatch.runner import run_command
from skipwatch.workdir import read_model, write_model

# the five rubric keys, read from the Critique.scores key Literal so they never drift
RUBRIC: tuple[str, ...] = get_args(get_args(Critique.model_fields["scores"].annotation)[0])
M = TypeVar("M", bound=BaseModel)


def _read(path: Path, cls: type[M]) -> M:
    if not path.is_file():
        raise SkipwatchError(ExitCode.CHECK_FAILED, f"{path.name} missing: {path}")
    try:
        return read_model(path, cls)
    except ValidationError as exc:
        err = exc.errors()[0]
        where = field_path(err["loc"])
        raise SkipwatchError(
            ExitCode.CHECK_FAILED,
            f"{path.name} invalid: " + (f"{where}: " if where else "") + err["msg"],
        ) from exc
    except ValueError as exc:
        raise SkipwatchError(
            ExitCode.CHECK_FAILED, f"{path.name} invalid: {type(exc).__name__}"
        ) from exc


def _validate_critique(work: Path, skill: Path) -> int:
    work = home_work_or_pack_folder(work)
    skill_md = skill / "SKILL.md"
    if not skill_md.is_file():
        raise SkipwatchError(ExitCode.NO_CONTENT, f"{skill_md} not found")
    path = work / "critique.json"
    critique = _read(path, Critique)
    for key in RUBRIC:
        if key not in critique.scores:
            raise SkipwatchError(ExitCode.CHECK_FAILED, f"critique.json misses rubric line {key}")
    for key, value in critique.scores.items():
        if not 1 <= value <= 10:
            raise SkipwatchError(
                ExitCode.CHECK_FAILED, f"critique.json scores {key} {value}, outside 1 to 10"
            )
    steps = len(skillmd.parse(skill_md.read_text(encoding="utf-8")).steps)
    for fix in critique.fixes:
        if not 0 <= fix.step <= steps:
            raise SkipwatchError(
                ExitCode.CHECK_FAILED, f"fix names step {fix.step}, the skill has {steps}"
            )
    score = round(mean(critique.scores.values()), 1)
    write_model(path, critique.model_copy(update={"score": score}))
    progress(f"critique valid: score {score}, {len(critique.fixes)} fixes")
    return 0


def _validate_test(work: Path) -> int:
    work = home_work_or_pack_folder(work)
    report = _read(work / "test-report.json", TesterReport)
    line = "Test run: " + report.outcome
    if report.outcome != "completed":
        line += f" at step {report.step} ({' '.join(report.detail.split())})"
    typer.echo(line)
    return 0


def register(app: typer.Typer) -> None:
    @app.command("validate-critique")
    def _critique(
        work: Annotated[Path, typer.Option("--work", help="The run's work folder.")],
        skill: Annotated[Path, typer.Option("--skill", help="The staged skill folder.")],
    ):
        """Check critique.json against the staged skill and rewrite its score. Exit 1 if bad."""
        run_command(lambda: _validate_critique(work, skill))

    @app.command("validate-test")
    def _test(
        work: Annotated[Path, typer.Option("--work", help="The run's work folder.")],
    ):
        """Check test-report.json and print its one Test run: line. Exit 1 if bad."""
        run_command(lambda: _validate_test(work))
