from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from skipwatch.config import load_config
from skipwatch.export import run_exports
from skipwatch.listing import locate
from skipwatch.output import emit_json, progress
from skipwatch.runner import run_command


def _export(skill: str, provider: str | None, force: bool, json_out: bool) -> int:
    folder = locate(skill, Path.cwd(), Path.home())
    result = run_exports(folder, provider, load_config(), datetime.now(UTC), force=force)
    if not result.results:
        progress("no exports enabled")
    for item in result.results:
        progress(f"{item.provider}: {item.detail if item.skipped else item.location}")
    if json_out:
        emit_json(result)
    return 0


def register(app: typer.Typer) -> None:
    @app.command("export")
    def _cmd(
        skill: Annotated[str, typer.Argument(help="An installed skill's name or folder.")],
        provider: Annotated[
            str | None,
            typer.Option("--provider", help="Run this export (mem0 or notes) even if disabled."),
        ] = None,
        force: bool = typer.Option(False, "--force", help="Export even if unchanged."),
        json_out: bool = typer.Option(False, "--json", help="Print the result as JSON."),
    ):
        """Export an installed skill to the exports enabled in config.toml."""
        run_command(lambda: _export(skill, provider, force, json_out))
