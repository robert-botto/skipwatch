import importlib
import pkgutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Annotated

import typer

# typer 0.27 vendors click and does not re-export UsageError; test_cli pins this import.
from typer._click.exceptions import ClickException, UsageError

from skipwatch import __version__, commands, config, stagelog
from skipwatch.errors import ExitCode
from skipwatch.runner import run_command

__all__ = ["app", "main", "run_command"]

app = typer.Typer(add_completion=False, help="SkipWatch engine.")


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Print the version."),
    log: Annotated[
        Path | None,
        typer.Option(
            "--log",
            help="Send progress to this file; at the end print rc, elapsed and its last 3 lines.",
        ),
    ] = None,
    home: Annotated[
        str | None,
        typer.Option(
            "--home",
            help="The SkipWatch home for this call (as SKIPWATCH_HOME; this wins over it).",
        ),
    ] = None,
) -> None:
    if home is not None:
        config.set_home_option(home)
        ctx.call_on_close(lambda: config.set_home_option(None))
    if log is not None:
        stagelog.start(log)
        ctx.call_on_close(stagelog.stop)
    if version:
        typer.echo(__version__)
        raise typer.Exit(0)
    if ctx.invoked_subcommand is None:
        raise UsageError("Missing command.", ctx)


def _register_all(target: typer.Typer, package: ModuleType) -> None:
    """Call register(target) on every module in package that defines it, in name order."""
    for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda m: m.name):
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        register = getattr(module, "register", None)
        if register is not None:
            register(target)


_register_all(app, commands)


def _dispatch() -> int:
    try:
        code = app(standalone_mode=False)
    except UsageError as exc:
        exc.show()
        return ExitCode.USAGE
    except ClickException as exc:
        exc.show()
        return exc.exit_code
    except typer.Abort:
        print("Aborted!", file=sys.stderr)
        return 1
    return code if isinstance(code, int) else 0


def main() -> None:
    """Console entry point. Usage errors exit 64 so they never read as exit 2 (unsupported)."""
    try:
        code = _dispatch()
    except KeyboardInterrupt:
        stagelog.report(130)
        raise
    except BaseException:
        stagelog.report(1)
        raise
    stagelog.report(code)
    sys.exit(code)
