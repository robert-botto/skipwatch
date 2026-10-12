from pathlib import Path
from typing import Annotated

import typer

from skipwatch.listing import locate
from skipwatch.output import emit_json, progress
from skipwatch.pack import pack_skill
from skipwatch.runner import run_command


def _skill_dir(skill: str) -> Path:
    """A folder holding skipwatch.json, or an installed skill's name."""
    return locate(skill, Path.cwd(), Path.home())


def _pack(skill: str, out: Path | None, json_out: bool) -> int:
    result = pack_skill(_skill_dir(skill), out)
    kb = max(1, round(result.bytes / 1024))
    progress(f"Packed {result.name}: {result.files} files, {kb} KB, sha256 {result.sha256[7:19]}")
    progress(f"Wrote {result.path}")
    if json_out:
        emit_json(result)
    return 0


def register(app: typer.Typer) -> None:
    @app.command("pack")
    def _cmd(
        skill: Annotated[str, typer.Argument(help="An installed skill's folder or name.")],
        out: Annotated[
            Path | None,
            typer.Option("-o", "--out", help="The pack file (default ./<name>.skillpack.zip)."),
        ] = None,
        json_out: bool = typer.Option(False, "--json", help="Print the result as JSON."),
    ):
        """Pack an installed skill into a verified .skillpack.zip for sharing."""
        run_command(lambda: _pack(skill, out, json_out))
