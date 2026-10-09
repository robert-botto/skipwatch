import os
from datetime import date

import typer

from skipwatch import doctor
from skipwatch.config import skipwatch_home
from skipwatch.output import emit_json, progress
from skipwatch.runner import run_command
from skipwatch.workdir import write_model


def _doctor(json_out: bool) -> int:
    report = doctor.build_report(
        doctor.probe_machine(), date.today(), os.environ.get("CLAUDE_PLUGIN_ROOT")
    )
    for line in doctor.render_table(report):
        progress(line)
    home = skipwatch_home()
    home.mkdir(parents=True, exist_ok=True)
    write_model(home / "doctor.json", report)
    if json_out:
        emit_json(report)
    return 0  # R-TIER-1: exits 0 at every tier


def register(app: typer.Typer) -> None:
    @app.command("doctor")
    def _cmd(json_out: bool = typer.Option(False, "--json", help="Print the report as JSON.")):
        """Report the capability tier and what to install next. Installs nothing."""
        run_command(lambda: _doctor(json_out))
