from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.listing import locate
from skipwatch.manifest import MANIFEST_NAME
from skipwatch.models import Manifest
from skipwatch.output import emit_json, progress
from skipwatch.runner import run_command
from skipwatch.share import share_text


def _share(skill: str, json_out: bool) -> int:
    folder = locate(skill, Path.cwd(), Path.home())
    try:
        manifest = Manifest.model_validate_json((folder / MANIFEST_NAME).read_bytes())
    except (OSError, ValidationError, ValueError) as exc:
        raise SkipwatchError(
            ExitCode.UNSUPPORTED_SOURCE, f"{folder / MANIFEST_NAME} is not readable"
        ) from exc
    result = share_text(manifest)
    if json_out:
        emit_json(result)
    else:
        for line in result.text.split("\n"):
            progress(line)
    return 0


def register(app: typer.Typer) -> None:
    @app.command("share")
    def _cmd(
        skill: Annotated[str, typer.Argument(help="An installed skill's name or folder.")],
        json_out: bool = typer.Option(False, "--json", help="Print the result as JSON."),
    ):
        """Print a thank-you post for the skill's creator, with the install line."""
        run_command(lambda: _share(skill, json_out))
