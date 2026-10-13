import importlib
import os
import pkgutil
import sys
import traceback
from pathlib import Path
from types import ModuleType
from typing import Annotated

import typer

# typer 0.27 vendors click and does not re-export UsageError; test_cli pins this import.
from typer._click.exceptions import ClickException, UsageError

from skipwatch import __version__, commands, config, stagelog
from skipwatch.commands.workfiles import log_path
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.redact import redact_message
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
        given = Path(home).expanduser()
        # the skill's homes are ~/.skipwatch and <project>/.skipwatch; SKIPWATCH_HOME stays open
        if given.name != ".skipwatch" or given.is_symlink():
            print(
                f"--home refused: {home} is not a .skipwatch folder (or is a symlink)",
                file=sys.stderr,
            )
            raise typer.Exit(ExitCode.USAGE)
        config.set_home_option(home)
        ctx.call_on_close(lambda: config.set_home_option(None))
    if log is not None:
        try:
            log = log_path(log)  # after --home, before the file is opened or the command runs
        except SkipwatchError as exc:
            print(f"--log refused: {exc.message}", file=sys.stderr)
            raise typer.Exit(ExitCode.USAGE) from None
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


def _internal_error(exc: Exception) -> int:
    """An engine bug: one redacted line on stderr, the traceback only in --log or with
    SKIPWATCH_DEBUG=1, and exit 70 so the skill never reads it as a check or install failure."""
    first = (str(exc).splitlines() or [""])[0]
    line = redact_message(f"skipwatch: internal error: {type(exc).__name__}: {first}".rstrip())
    trace = redact_message("".join(traceback.format_exception(exc)))
    log = stagelog.active_path()
    if log is not None:
        try:
            stagelog.append(trace + line)
            line += f" (traceback in {log})"
        except OSError:
            pass  # the one line still goes out
        stagelog.report(ExitCode.INTERNAL_ERROR)
    elif os.environ.get("SKIPWATCH_DEBUG") == "1":
        print(trace, end="", file=sys.stderr)
    print(line, file=sys.stderr, flush=True)
    return ExitCode.INTERNAL_ERROR


def main() -> None:
    """Console entry point. Usage errors exit 64 so they never read as exit 2 (unsupported)."""
    try:
        code = _dispatch()
    except KeyboardInterrupt:
        stagelog.report(130)
        raise
    except Exception as exc:
        code = _internal_error(exc)
    except BaseException:
        stagelog.report(1)
        raise
    else:
        stagelog.report(code)
    sys.exit(code)
