import importlib
import pkgutil

import typer

from skipwatch import __version__, commands
from skipwatch.runner import run_command

__all__ = ["app", "main", "run_command"]

app = typer.Typer(no_args_is_help=True, add_completion=False, help="SkipWatch engine.")


@app.callback(invoke_without_command=True)
def _root(version: bool = typer.Option(False, "--version", help="Print the version.")) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit(0)


def _register_all() -> None:
    for info in sorted(pkgutil.iter_modules(commands.__path__), key=lambda m: m.name):
        module = importlib.import_module(f"{commands.__name__}.{info.name}")
        register = getattr(module, "register", None)
        if register is not None:
            register(app)


_register_all()


def main() -> None:
    app()
