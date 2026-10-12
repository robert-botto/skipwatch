"""target-free: whether an install target is free, as one stdout line (live finding: a run
read `test -e` exit 1 as "exists" and blocked --yes). Read-only: never creates or deletes."""

import os
import re
from pathlib import Path
from typing import Annotated

import typer

from skipwatch.checks.frontmatter import is_skill_name
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.runner import run_command

_HOME_VAR = re.compile(r"^\$(HOME|\{HOME\})(?=/|$)")


def _expand(raw: str) -> Path:
    """~ and a leading $HOME or ${HOME} resolved here, so the skill never quotes a tilde."""
    return Path(_HOME_VAR.sub(lambda _: str(Path.home()), raw)).expanduser()


def _target_free(to: str | None, name: str | None, target: str | None) -> int:
    if target is not None and to is None and name is None:
        path = _expand(target)
        if not path.is_absolute():
            raise SkipwatchError(ExitCode.USAGE, f"--target {target} is not an absolute path")
        if path.is_symlink():
            raise SkipwatchError(ExitCode.USAGE, f"--target {path} is a symlink")
    elif target is None and to is not None and name is not None:
        if not is_skill_name(name):
            raise SkipwatchError(ExitCode.USAGE, f"--name {name!r} is not a skill name")
        path = Path(os.path.abspath(_expand(to))) / name
    else:
        raise SkipwatchError(ExitCode.USAGE, "give --to and --name, or --target alone")
    # a dangling symlink counts as taken: install would refuse it too
    print(f"target {'exists' if os.path.lexists(path) else 'free'}: {path}")
    return 0


def register(app: typer.Typer) -> None:
    @app.command("target-free")
    def _cmd(
        to: Annotated[
            str | None, typer.Option("--to", help="The skills folder (~ and $HOME allowed).")
        ] = None,
        name: Annotated[str | None, typer.Option("--name", help="The skill name.")] = None,
        target: Annotated[
            str | None, typer.Option("--target", help="A full target path instead.")
        ] = None,
    ):
        """Print `target free: <path>` or `target exists: <path>`; exit 0 either way."""
        run_command(lambda: _target_free(to, name, target))
