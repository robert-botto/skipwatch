import sys

import typer

from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.output import progress
from skipwatch.redact import redact_text
from skipwatch.runner import run_command


def _redact(stdin: bool) -> int:
    if not stdin:
        raise SkipwatchError(ExitCode.USAGE, "redact needs --stdin (it only reads standard input)")
    # Bytes in, UTF-8 out: line endings are kept and invalid bytes become U+FFFD, so the
    # staged files the orchestrator writes with `redact --stdin < draft > staged` stay valid UTF-8.
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    text, reps = redact_text(raw)
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.flush()
    for rep in reps:
        progress(f"replaced {rep.count} {rep.kind} with {rep.placeholder}")
    return 0


def register(app: typer.Typer) -> None:
    @app.command("redact")
    def _cmd(
        stdin: bool = typer.Option(False, "--stdin", help="Redact standard input to stdout."),
    ):
        """Replace API keys, tokens and passwords with placeholders."""
        run_command(lambda: _redact(stdin))
