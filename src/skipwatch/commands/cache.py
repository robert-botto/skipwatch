from datetime import datetime

import typer

from skipwatch.cache import cache_status, clear_cache
from skipwatch.config import skipwatch_home
from skipwatch.output import emit_json, progress
from skipwatch.runner import run_command


def _cache(clear: bool, json_out: bool) -> int:
    home = skipwatch_home()
    if clear:
        result = clear_cache(home, datetime.now())
        progress(f"Cleared {len(result.removed)} item(s) from {home}")
    else:
        result = cache_status(home)
        progress(f"{result.cache_entries} cache entries, {result.work_folders} work folders")
    if json_out:
        emit_json(result)
    return 0


def register(app: typer.Typer) -> None:
    @app.command("cache")
    def _cmd(
        clear: bool = typer.Option(
            False, "--clear", help="Remove cache/ and work folders older than 7 days."
        ),
        json_out: bool = typer.Option(False, "--json", help="Print the result as JSON."),
    ):
        """Show or clear cached downloads and old work folders."""
        run_command(lambda: _cache(clear, json_out))
