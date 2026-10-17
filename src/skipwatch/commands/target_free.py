"""target-free: whether an install target is free, as one stdout line (live finding: a run
read `test -e` exit 1 as "exists" and blocked --yes). Read-only: never creates or deletes."""

import os
import re
from pathlib import Path
from typing import Annotated

import typer

from skipwatch.checks.frontmatter import is_skill_name
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.install import Scope, install_root, scope_target
from skipwatch.runner import run_command

_HOME_VAR = re.compile(r"^\$(HOME|\{HOME\})(?=/|$)")


def _expand(raw: str) -> Path:
    """~ and a leading $HOME or ${HOME} resolved here, so the skill never quotes a tilde. Both
    mean Path.home(), the home install uses: %USERPROFILE% on Windows, not a HOME variable."""
    return Path(_HOME_VAR.sub(lambda _: str(Path.home()), raw)).expanduser()


def _target_free(to: str | None, name: str | None, target: str | None, scope: Scope | None) -> int:
    if scope is not None and (to is not None or target is not None):
        raise SkipwatchError(ExitCode.USAGE, "--scope goes with --name alone, not --to or --target")
    if target is not None and to is None and name is None:
        path = _expand(target)
        if not path.is_absolute():
            raise SkipwatchError(ExitCode.USAGE, f"--target {target} is not an absolute path")
        if path.is_symlink():
            raise SkipwatchError(ExitCode.USAGE, f"--target {path} is a symlink")
    elif target is None and to is not None and name is not None:
        if not is_skill_name(name):
            raise SkipwatchError(ExitCode.USAGE, f"--name {name!r} is not a skill name")
        path = install_root(Path.cwd() / _expand(to)) / name
    elif target is None and to is None and name is not None:
        if not is_skill_name(name):
            raise SkipwatchError(ExitCode.USAGE, f"--name {name!r} is not a skill name")
        path, _ = scope_target(scope, name, Path.cwd(), Path.home())
    else:
        raise SkipwatchError(
            ExitCode.USAGE, "give --name (with --scope or --to), or --target alone"
        )
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
        scope: Annotated[
            Scope | None,
            typer.Option(
                "--scope",
                help="user, project or agents, resolved as install does. Default from config.",
            ),
        ] = None,
    ):
        """Print `target free: <path>` or `target exists: <path>`; exit 0 either way."""
        run_command(lambda: _target_free(to, name, target, scope))
