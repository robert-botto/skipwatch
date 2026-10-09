import importlib
import pkgutil
import sys
from types import ModuleType

import typer

# typer 0.27 vendors click and does not re-export UsageError; test_cli pins this import.
from typer._click.exceptions import ClickException, UsageError

from skipwatch import __version__, commands
from skipwatch.errors import ExitCode
from skipwatch.runner import run_command

__all__ = ["app", "main", "run_command"]

app = typer.Typer(add_completion=False, help="SkipWatch engine.")


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Print the version."),
) -> None:
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


def main() -> None:
    """Console entry point. Usage errors exit 64 so they never read as exit 2 (unsupported)."""
    try:
        code = app(standalone_mode=False)
    except UsageError as exc:
        exc.show()
        sys.exit(ExitCode.USAGE)
    except ClickException as exc:
        exc.show()
        sys.exit(exc.exit_code)
    except typer.Abort:
        print("Aborted!", file=sys.stderr)
        sys.exit(1)
    sys.exit(code if isinstance(code, int) else 0)
