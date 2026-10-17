from pathlib import Path
from typing import Annotated

import typer

from skipwatch.checks.runner import run_all
from skipwatch.commands.workfiles import home_work_or_pack_folder, path_under
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.output import emit_json, progress
from skipwatch.runner import run_command


def _check(staging: Path, work: Path | None, json_out: bool) -> int:
    work = home_work_or_pack_folder(work or staging.parent.parent)
    staging = path_under(work, "staging", staging, "staging folder")
    if not (staging / "SKILL.md").is_file():
        raise SkipwatchError(ExitCode.USAGE, f"{staging} has no SKILL.md")
    if not (work / "ingest.json").is_file():
        raise SkipwatchError(
            ExitCode.USAGE, f"{work} has no ingest.json; pass --work <work folder>"
        )
    try:
        report = run_all(staging, work)
    except SkipwatchError:
        raise
    except Exception as exc:
        # A bug must never read as "check failed" (1): distinct code, and say what broke.
        progress(f"internal error in skipwatch check: {type(exc).__name__}: {exc}")
        return ExitCode.INTERNAL_ERROR
    for result in report.results:
        if result.check == "safety":
            progress(f"safety: {len(result.flags)} flag(s)")
        else:
            state = "ok" if result.ok else "FAILED"
            progress(f"{result.check}: {state} ({len(result.items)} item(s))")
    if json_out:
        emit_json(report)
    if not report.passed:
        return ExitCode.CHECK_FAILED
    if any(r.flags for r in report.results):
        return ExitCode.SAFETY_FLAGS
    return ExitCode.OK


def register(app: typer.Typer) -> None:
    @app.command("check")
    def _cmd(
        staging: Annotated[Path, typer.Argument(help="The staging skill folder.")],
        work: Annotated[
            Path | None,
            typer.Option(
                "--work", help="The work folder (default: two levels above the staging folder)."
            ),
        ] = None,
        json_out: bool = typer.Option(False, "--json", help="Print the report as JSON."),
    ):
        """Run the six checks, redact the staging folder and write check-report.json."""
        run_command(lambda: _check(staging, work, json_out))
