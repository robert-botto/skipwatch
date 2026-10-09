from typing import Annotated

import typer

from skipwatch.adapters.base import IngestOptions
from skipwatch.models import ProbeResult
from skipwatch.output import emit_json, progress
from skipwatch.probe import probe
from skipwatch.runner import run_command


def _clock(seconds: float | None) -> str:
    if seconds is None:
        return "?:??"
    total = round(seconds)
    return f"{total // 60}:{total % 60:02d}"


def summary(result: ProbeResult) -> str:
    captions = "yes" if result.captions_available else "no"
    estimate = f"{result.estimated_run_s}s" if result.estimated_run_s is not None else "unknown"
    title = result.title or result.value
    return f'Probe: "{title}" {_clock(result.duration_s)}, captions {captions}, est. {estimate}'


def _probe(value: str, opts: IngestOptions, json_out: bool) -> int:
    result = probe(value, opts)
    progress(summary(result))
    if json_out:
        emit_json(result)
    return 0


def register(app: typer.Typer) -> None:
    @app.command("probe")
    def _cmd(
        source: Annotated[str, typer.Argument(help="A URL or a local video or audio file.")],
        cookies_from_browser: Annotated[
            str | None,
            typer.Option(
                "--cookies-from-browser", help="Browser to read cookies from (explicit only)."
            ),
        ] = None,
        json_out: Annotated[bool, typer.Option("--json", help="Print the probe as JSON.")] = False,
    ):
        """Read a source's metadata without downloading or writing anything."""
        opts = IngestOptions(provider="free", cookies_from_browser=cookies_from_browser)
        run_command(lambda: _probe(source, opts, json_out))
