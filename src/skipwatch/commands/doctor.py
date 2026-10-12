import math
import os
import time
from datetime import date
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from skipwatch import doctor
from skipwatch.config import skipwatch_home
from skipwatch.models import DoctorReport
from skipwatch.output import emit_json, progress
from skipwatch.runner import run_command
from skipwatch.workdir import read_model, write_model


def _cached(path: Path, max_age_hours: float) -> DoctorReport | None:
    """doctor.json when its mtime is under max_age_hours old and it still reads, else None."""
    try:
        age_s = time.time() - path.stat().st_mtime
        if not 0 <= age_s < max_age_hours * 3600:  # a future mtime is stale too
            return None
        return read_model(path, DoctorReport)
    except (OSError, ValidationError, ValueError):
        return None


def _finite_hours(value: float | None) -> float | None:
    if value is not None and not math.isfinite(value):
        raise typer.BadParameter("must be a finite number of hours")
    return value


def _doctor(json_out: bool, max_age_hours: float | None) -> int:
    home = skipwatch_home()
    report = None if max_age_hours is None else _cached(home / "doctor.json", max_age_hours)
    fresh = report is None
    if report is None:
        report = doctor.build_report(
            doctor.probe_machine(), date.today(), os.environ.get("CLAUDE_PLUGIN_ROOT")
        )
    for line in doctor.render_table(report):
        progress(line)
    if fresh:
        home.mkdir(parents=True, exist_ok=True)
        write_model(home / "doctor.json", report)
    if json_out:
        emit_json(report)
    return 0  # R-TIER-1: exits 0 at every tier


def register(app: typer.Typer) -> None:
    @app.command("doctor")
    def _cmd(
        json_out: bool = typer.Option(False, "--json", help="Print the report as JSON."),
        max_age_hours: Annotated[
            float | None,
            typer.Option(
                "--max-age-hours",
                min=0,
                callback=_finite_hours,
                help="Reuse doctor.json when it is younger than this; else rebuild it.",
            ),
        ] = None,
    ):
        """Report the capability tier and what to install next. Installs nothing."""
        run_command(lambda: _doctor(json_out, max_age_hours))
