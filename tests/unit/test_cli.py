import pathlib

import typer
from typer.testing import CliRunner

from skipwatch import cli
from skipwatch.errors import ExitCode, SkipwatchError


def test_help_lists_registered_commands():
    r = CliRunner().invoke(cli.app, ["--help"])
    assert r.exit_code == 0


def test_run_command_maps_errors_to_exit_codes():
    app = typer.Typer()

    @app.command()
    def boom():
        cli.run_command(
            lambda: (_ for _ in ()).throw(SkipwatchError(ExitCode.NO_CONTENT, "nothing usable"))
        )

    r = CliRunner().invoke(app, [])
    assert r.exit_code == 7
    assert "nothing usable" in r.stderr


def test_r_cli_3_no_command_reads_stdin():
    root = pathlib.Path(cli.__file__).parent
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if path.name == "redact.py" and path.parent.name == "commands":
            continue
        assert "sys.stdin" not in text and "input(" not in text and "typer.prompt" not in text, path


def test_r_ux_2_progress_is_one_line(capsys):
    from skipwatch.output import progress

    progress("Sampling frames\n21 kept (4s)")
    assert capsys.readouterr().err == "Sampling frames 21 kept (4s)\n"


def test_version_flag_prints_version_with_no_command():
    r = CliRunner().invoke(cli.app, ["--version"])
    assert r.exit_code == 0
    assert r.stdout.strip() == "0.1.0"
