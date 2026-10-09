"""new-work: create a run's work folder where the engine will look for it.

The orchestrator takes <W> only from this command's output, so the folder always sits under
the same home the engine uses (SKIPWATCH_HOME, else ~/.skipwatch), never a hand-built path.
"""

import json
import re
import time
from datetime import datetime
from typing import Annotated

import typer

from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.output import progress
from skipwatch.runner import run_command
from skipwatch.workdir import WorkDir, new_work_path

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")


def _new_work(slug: str, json_out: bool) -> int:
    if not SLUG_RE.match(slug):
        raise SkipwatchError(
            ExitCode.USAGE,
            f"bad slug {slug!r}: lowercase letters, digits and hyphens, 1 to 80 characters",
        )
    path = new_work_path(slug, datetime.now()).absolute()
    while path.exists():  # two runs in the same second: take the next free second
        time.sleep(1)
        path = new_work_path(slug, datetime.now()).absolute()
    work = WorkDir(path)
    work.ensure()
    (path / "logs").mkdir()
    (path / "draft").mkdir()
    progress(f"Work folder: {path}")
    print(json.dumps({"work": str(path)}) if json_out else str(path))
    return 0


def register(app: typer.Typer) -> None:
    @app.command("new-work")
    def _cmd(
        slug: Annotated[str, typer.Option("--slug", help="Lowercase, hyphenated run name.")],
        json_out: bool = typer.Option(False, "--json", help='Print {"work": <path>}.'),
    ):
        """Create a work folder under the engine's home and print its absolute path."""
        run_command(lambda: _new_work(slug, json_out))
