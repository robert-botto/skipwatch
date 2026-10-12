import os
import sys
from pathlib import Path
from typing import Annotated

import typer

from skipwatch.commands.workfiles import home_work_or_pack_folder, path_under
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.output import progress
from skipwatch.redact import redact_text
from skipwatch.runner import run_command
from skipwatch.workdir import write_bytes_atomic


def _report(raw: str) -> str:
    text, reps = redact_text(raw)
    for rep in reps:
        progress(f"replaced {rep.count} {rep.kind} with {rep.placeholder}")
    return text


def _redact_stdin() -> int:
    # Bytes in, UTF-8 out: line endings are kept and invalid bytes become U+FFFD, so
    # `redact --stdin < draft > staged` stays valid UTF-8.
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    sys.stdout.buffer.write(_report(raw).encode("utf-8"))
    sys.stdout.buffer.flush()
    return 0


def _redact_file(work: Path, src: Path, out: Path) -> int:
    """One draft file to staging with no shell redirect (skill audit 5 fix 5): every path is
    checked before anything is read or written."""
    work = home_work_or_pack_folder(work)
    src = path_under(work, "draft", src, "--in")
    out = path_under(work, "staging", out, "--out")
    if not src.is_file():
        raise SkipwatchError(ExitCode.USAGE, f"--in {src} is not a file")
    if out.is_dir():
        raise SkipwatchError(ExitCode.USAGE, f"--out {out} is a folder")
    try:
        fd = os.open(src, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            raw = stream.read()
    except OSError as exc:
        raise SkipwatchError(ExitCode.USAGE, f"--in {src} cannot be read: {exc}") from exc
    text = _report(raw.decode("utf-8", errors="replace"))
    out.parent.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(out, text.encode("utf-8"))
    progress(f"Redacted: {out}")
    return 0


def _redact(stdin: bool, work: Path | None, src: Path | None, out: Path | None) -> int:
    file_mode = (work, src, out)
    if stdin and all(p is None for p in file_mode):
        return _redact_stdin()
    if not stdin and work is not None and src is not None and out is not None:
        return _redact_file(work, src, out)
    raise SkipwatchError(
        ExitCode.USAGE, "redact needs either --stdin alone or all of --work, --in and --out"
    )


def register(app: typer.Typer) -> None:
    @app.command("redact")
    def _cmd(
        stdin: bool = typer.Option(False, "--stdin", help="Redact standard input to stdout."),
        work: Annotated[
            Path | None, typer.Option("--work", help="The work folder holding --in and --out.")
        ] = None,
        src: Annotated[
            Path | None, typer.Option("--in", help="A file under <work>/draft to redact.")
        ] = None,
        out: Annotated[
            Path | None,
            typer.Option("--out", help="Where to write it, under <work>/staging (folders made)."),
        ] = None,
    ):
        """Replace API keys, tokens and passwords with placeholders."""
        run_command(lambda: _redact(stdin, work, src, out))
