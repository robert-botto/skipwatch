"""mark: record the stages that run in the Claude session (read, distill, critique, review).

Engine stages mark themselves through run_stage; these four have no engine command, so the
orchestrator marks them here and stages.json carries their timings for resume (R-WORK-1).
"""

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.output import progress
from skipwatch.runner import run_command
from skipwatch.workdir import WorkDir


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


def register(app: typer.Typer) -> None:
    @app.command("mark")
    def _cmd(
        work: Annotated[Path, typer.Option("--work", help="The run's work folder.")],
        stage: Annotated[ClaudeStage, typer.Option("--stage", help="A stage run by Claude.")],
        status: Annotated[MarkStatus, typer.Option("--status", help="The stage's new status.")],
    ):
        """Record the status of a stage that runs in the Claude session."""
        run_command(lambda: _mark(work, stage, status))
