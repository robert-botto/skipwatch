from pathlib import Path
from typing import Annotated

import typer

from skipwatch.frames import run_frames
from skipwatch.output import emit_json, progress
from skipwatch.runner import run_command
from skipwatch.workdir import WorkDir


def _frames(
    work_dir: Path, per_minute: int | None, max_frames: int | None, dense: bool, json_out: bool
) -> int:
    work = WorkDir(work_dir)
    work.ensure()
    progress("Sampling frames")
    result = run_frames(work, per_minute, max_frames, dense)
    cues = sum(1 for f in result.frames if f.reason == "cue")
    progress(f"Kept {len(result.frames)} frame(s), {cues} from spoken cues")
    if json_out:
        emit_json(result)
    return 0


def register(app: typer.Typer) -> None:
    @app.command("frames")
    def _cmd(
        work: Annotated[
            Path,
            typer.Option("--work", exists=True, file_okay=False, help="The run's work folder."),
        ],
        per_minute: int | None = typer.Option(
            None, "--per-minute", min=1, help="Frame budget per minute (default 3)."
        ),
        max_frames: int | None = typer.Option(
            None, "--max", min=1, help="Frame budget in total (default 60)."
        ),
        dense: bool = typer.Option(False, "--dense", help="Sample 6 frames per minute."),
        json_out: bool = typer.Option(False, "--json", help="Print frames.json to stdout."),
    ):
        """Sample, dedup and budget frames; writes frames/ and frames.json."""
        run_command(lambda: _frames(work, per_minute, max_frames, dense, json_out))
