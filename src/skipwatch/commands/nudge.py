"""nudge: the star line after an install, printed once per SkipWatch home.

The marker file replaces the skill's `test -e` and `touch` (skill audit 4 fix 1). A nudge
never fails a run: every outcome exits 0.
"""

import typer

from skipwatch.config import skipwatch_home
from skipwatch.runner import run_command

MARKER = ".star-nudged"
STAR_LINE = (
    "If this saved you an hour, a star helps others find it: "
    "https://github.com/robert-botto/skipwatch"
)


def _nudge() -> int:
    marker = skipwatch_home() / MARKER
    try:
        if marker.exists():
            return 0
    except OSError:
        return 0
    typer.echo(STAR_LINE)
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    except OSError:
        pass  # printed again next time, as the shell version did
    return 0


def register(app: typer.Typer) -> None:
    @app.command("nudge")
    def _cmd():
        """Print the star line once per SkipWatch home; print nothing afterwards."""
        run_command(_nudge)
