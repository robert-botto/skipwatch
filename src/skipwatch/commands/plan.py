from pathlib import Path
from typing import Annotated

import typer

from skipwatch.commands.workfiles import home_work_or_pack_folder
from skipwatch.output import emit_json, progress
from skipwatch.plan import DEFAULT_BATCH_SIZE, run_plan
from skipwatch.runner import run_command
from skipwatch.workdir import WorkDir


def _plan(work_dir: Path, batch_size: int, json_out: bool) -> int:
    work = WorkDir(home_work_or_pack_folder(work_dir))
    result = run_plan(work, batch_size)
    frames = sum(len(b.frame_ids) for b in result.batches)
    progress(f"Planned {len(result.batches)} reader batch(es) for {frames} frame(s)")
    if json_out:
        emit_json(result)
    return 0


def register(app: typer.Typer) -> None:
    @app.command("plan")
    def _cmd(
        work: Annotated[
            Path,
            typer.Option("--work", exists=True, file_okay=False, help="The run's work folder."),
        ],
        batch_size: int = typer.Option(
            DEFAULT_BATCH_SIZE, "--batch-size", min=1, help="Frames per reader batch."
        ),
        json_out: bool = typer.Option(False, "--json", help="Print batches.json to stdout."),
    ):
        """Split the kept frames into reader batches; writes batches.json."""
        run_command(lambda: _plan(work, batch_size, json_out))
