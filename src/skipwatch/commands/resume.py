from pathlib import Path
from typing import Annotated

import typer

from skipwatch.commands.workfiles import home_work_or_pack_folder
from skipwatch.config import skipwatch_home
from skipwatch.models import ResumeResult
from skipwatch.output import emit_json, progress
from skipwatch.resume import newest_incomplete, resume_info, skill_name
from skipwatch.runner import run_command


def _resume(work: Path | None, json_out: bool) -> int:
    if work is not None:
        work = home_work_or_pack_folder(work, require_stages=False)
    else:
        work = newest_incomplete(skipwatch_home())
    if work is None:
        progress("Resume: nothing to resume")
        result = ResumeResult(work="", next_stage=None)
    else:
        result = resume_info(work)
        done = len(result.completed)
        if result.next_stage is None:
            progress(f"Resume: {work} is complete ({done} stages done)")
        else:
            progress(f"Resume: {work} at {result.next_stage} ({done} stages done)")
        skill = skill_name(work, result.run)
        if skill is not None:
            progress(f"Resume: skill {skill} ({work / 'staging' / skill})")
    if json_out:
        emit_json(result)
    return 0


def register(app: typer.Typer) -> None:
    @app.command("resume")
    def _cmd(
        work: Annotated[
            Path | None,
            typer.Argument(help="The work folder (default: the newest unfinished run)."),
        ] = None,
        json_out: bool = typer.Option(False, "--json", help="Print the result as JSON."),
    ):
        """Name the next stage of an unfinished run, without changing anything."""
        run_command(lambda: _resume(work, json_out))
