import tempfile
from pathlib import Path
from typing import Annotated

import typer

from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import UnpackResult
from skipwatch.output import emit_json, progress
from skipwatch.pack import unpack
from skipwatch.providers.pack_fetch import fetch_pack
from skipwatch.runner import run_command


def _from_source(source: str, work: Path | None) -> UnpackResult:
    lowered = source.lower()
    if lowered.startswith("http://"):
        raise SkipwatchError(ExitCode.UNSUPPORTED_SOURCE, "pack URLs must be https")
    if lowered.startswith("https://"):
        with tempfile.TemporaryDirectory(prefix="skipwatch-pack-") as tmp:
            return unpack(fetch_pack(source, Path(tmp)), work, fetched_from=source)
    path = Path(source)
    if not path.is_file():
        raise SkipwatchError(
            ExitCode.UNSUPPORTED_SOURCE, f"{source} is not a pack file or an https URL"
        )
    return unpack(path, work)


def _unpack(source: str, work: Path | None, json_out: bool) -> int:
    result = _from_source(source, work)
    progress(
        f"Pack verified: {result.name}, {result.files} files, sha256 {result.pack_sha256[7:19]}"
    )
    progress(f"Unpacked to {result.staging}")
    if json_out:
        emit_json(result)
    return 0


def register(app: typer.Typer) -> None:
    @app.command("unpack")
    def _cmd(
        source: Annotated[str, typer.Argument(help="A .skillpack.zip file or an https URL.")],
        work: Annotated[
            Path | None,
            typer.Option(
                "--work",
                help="A new folder directly under $SKIPWATCH_HOME/packs/ (default: <name>-<time>).",
            ),
        ] = None,
        json_out: bool = typer.Option(False, "--json", help="Print the result as JSON."),
    ):
        """Verify a pack and lay it out in a pack work folder for check and review."""
        run_command(lambda: _unpack(source, work, json_out))
