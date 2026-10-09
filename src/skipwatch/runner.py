"""run_command lives here, not in cli.py, so command modules can import it without a cycle.

cli.py imports every module in skipwatch.commands at import time. If a command module imported
run_command from cli and was itself imported first, cli would see it half-initialised and skip
its register(). Command modules use `from skipwatch.runner import run_command`.
"""

from collections.abc import Callable

import typer

from skipwatch.errors import SkipwatchError
from skipwatch.output import progress


def run_command(fn: Callable[[], int | None]) -> None:
    try:
        code = fn() or 0
    except SkipwatchError as exc:
        progress(exc.message)
        raise typer.Exit(int(exc.code)) from exc
    raise typer.Exit(code)
