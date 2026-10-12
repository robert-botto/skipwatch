from pathlib import Path
from typing import Annotated

import typer

from skipwatch.commands.workfiles import home_work_or_pack_folder, path_under
from skipwatch.output import progress
from skipwatch.runner import run_command
from skipwatch.skillframes import copy_frames


def _copy(work: Path, to: Path, ids: list[str]) -> int:
    work = home_work_or_pack_folder(work)
    to = path_under(work, "staging", to, "--to")
    out = copy_frames(work, to, ids)
    progress(f"Copied {len(out)} frame(s) to {to} at 960 wide")
    return 0


def register(app: typer.Typer) -> None:
    @app.command("copy-frames")
    def _cmd(
        work: Annotated[Path, typer.Option("--work", help="The run's work folder.")],
        to: Annotated[Path, typer.Option("--to", help="The skill's frames folder.")],
        ids: Annotated[list[str], typer.Argument(help="Frame ids from frames.json.")],
    ):
        """Copy frames into a skill, scaled to 960 wide (at most 8 per skill)."""
        run_command(lambda: _copy(work, to, ids))
