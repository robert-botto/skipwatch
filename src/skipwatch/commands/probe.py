from pathlib import Path
from typing import Annotated

import typer

from skipwatch.adapters.base import IngestOptions
from skipwatch.commands.workfiles import home_work_or_pack_folder, path_under
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import ProbeResult
from skipwatch.output import emit_json, progress
from skipwatch.probe import probe
from skipwatch.runner import run_command
from skipwatch.workdir import write_model


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


def _out_path(work: Path | None, out: Path | None) -> Path | None:
    """--out resolved inside <work>/logs (skill audit 5 fix 5), checked before probing."""
    if work is None and out is None:
        return None
    if work is None or out is None:
        raise SkipwatchError(ExitCode.USAGE, "--work and --out go together")
    path = path_under(home_work_or_pack_folder(work), "logs", out, "--out")
    if path.is_dir():
        raise SkipwatchError(ExitCode.USAGE, f"--out {path} is a folder")
    return path


def _probe(
    value: str, opts: IngestOptions, json_out: bool, work: Path | None, out: Path | None
) -> int:
    out_path = _out_path(work, out)
    result = probe(value, opts)
    progress(summary(result))
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_model(out_path, result)
    elif json_out:
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
        work: Annotated[
            Path | None, typer.Option("--work", help="The work folder whose logs/ holds --out.")
        ] = None,
        out: Annotated[
            Path | None,
            typer.Option("--out", help="Write the JSON here, under <work>/logs, not stdout."),
        ] = None,
    ):
        """Read a source's metadata without downloading; it writes nothing but --out."""
        opts = IngestOptions(provider="free", cookies_from_browser=cookies_from_browser)
        run_command(lambda: _probe(source, opts, json_out, work, out))
