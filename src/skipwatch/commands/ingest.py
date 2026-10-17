from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from skipwatch.adapters.base import IngestOptions
from skipwatch.commands.workfiles import home_work_or_pack_folder
from skipwatch.ingest import run_ingest
from skipwatch.output import emit_json, progress
from skipwatch.runner import run_command
from skipwatch.workdir import WorkDir


class Provider(StrEnum):
    auto = "auto"
    free = "free"
    treg = "treg"


def _ingest(value: str, work: Path, opts: IngestOptions, json_out: bool) -> int:
    progress(f"Ingesting {value}")
    bundle = run_ingest(value, WorkDir(home_work_or_pack_folder(work)), opts)
    captions = bundle.context.captions_path or "none"
    progress(f"Ingested {bundle.source.title or value} (captions: {captions})")
    if json_out:
        emit_json(bundle)
    return 0


def register(app: typer.Typer) -> None:
    @app.command("ingest")
    def _cmd(
        source: Annotated[str, typer.Argument(help="A URL or a local video or audio file.")],
        work: Annotated[Path, typer.Option("--work", help="The work folder for this run.")],
        provider: Annotated[
            Provider, typer.Option("--provider", help="Content provider.")
        ] = Provider.auto,
        max_height: Annotated[
            int, typer.Option("--max-height", help="Download height cap.")
        ] = 1080,
        cookies_from_browser: Annotated[
            str | None,
            typer.Option(
                "--cookies-from-browser", help="Browser to read cookies from (explicit only)."
            ),
        ] = None,
        json_out: Annotated[
            bool, typer.Option("--json", help="Print ingest.json to stdout.")
        ] = False,
    ):
        """Fetch a source into the work folder and write ingest.json."""
        opts = IngestOptions(
            provider=provider.value,
            max_height=max_height,
            cookies_from_browser=cookies_from_browser,
        )
        run_command(lambda: _ingest(source, work, opts, json_out))
