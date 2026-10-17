from pathlib import Path
from typing import Annotated

import typer

from skipwatch.install import Scope, install
from skipwatch.output import emit_json, progress
from skipwatch.runner import run_command


def _install(
    staging: Path, scope: Scope | None, to: Path | None, force: bool, json_out: bool
) -> int:
    result = install(staging, scope, to, force)
    if result.backup:
        progress(f"Backed up the previous copy to {result.backup}")
    progress(f"Installed {result.name} to {result.path}")
    if json_out:
        emit_json(result)
    return 0


def register(app: typer.Typer) -> None:
    @app.command("install")
    def _cmd(
        staging: Annotated[Path, typer.Argument(help="The checked staging folder of the skill.")],
        scope: Annotated[
            Scope | None,
            typer.Option("--scope", help="user, project or agents. Default from config (user)."),
        ] = None,
        to: Annotated[
            Path | None, typer.Option("--to", help="Install under this folder instead.")
        ] = None,
        force: bool = typer.Option(
            False, "--force", help="Replace an existing skill (a backup is made first)."
        ),
        json_out: bool = typer.Option(False, "--json", help="Print the result as JSON."),
    ):
        """Install a checked skill into a skills folder."""
        run_command(lambda: _install(staging, scope, to, force, json_out))
