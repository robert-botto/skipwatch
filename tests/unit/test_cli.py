import ast
import importlib
import pathlib
import sys

import pytest
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
    assert r.stdout.strip() == "0.1.1"


def _register_fake_commands(tmp_path, monkeypatch):
    pkg = tmp_path / "fakecmds"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "hello.py").write_text(
        "import typer\n\n\n"
        "def register(app: typer.Typer) -> None:\n"
        "    @app.command('hello')\n"
        "    def _hello() -> None:\n"
        "        typer.echo('hi from fake')\n",
        encoding="utf-8",
    )
    (pkg / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    return importlib.import_module("fakecmds")


def test_register_all_registers_every_module_with_register(tmp_path, monkeypatch):
    package = _register_fake_commands(tmp_path, monkeypatch)
    app = typer.Typer()

    @app.callback()
    def _root() -> None:
        pass

    cli._register_all(app, package)
    r = CliRunner().invoke(app, ["hello"])
    assert r.exit_code == 0 and r.stdout.strip() == "hi from fake"


def _imports_skipwatch_cli(path: pathlib.Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(a.name == "skipwatch.cli" for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and (
            node.module == "skipwatch.cli"
            or (node.module == "skipwatch" and any(a.name == "cli" for a in node.names))
        ):
            return True
    return False


@pytest.mark.parametrize(
    "source",
    ["from skipwatch.cli import run_command", "import skipwatch.cli", "from skipwatch import cli"],
)
def test_cli_import_scan_catches(tmp_path, source):
    path = tmp_path / "cmd.py"
    path.write_text(source + "\n", encoding="utf-8")
    assert _imports_skipwatch_cli(path)


def test_commands_import_runner_not_cli():
    """cli imports every command module; a command importing cli back can lose its register()."""
    root = pathlib.Path(cli.__file__).parent / "commands"
    offenders = [p.name for p in root.rglob("*.py") if _imports_skipwatch_cli(p)]
    assert not offenders, f"use skipwatch.runner.run_command instead: {offenders}"


def _run_main(monkeypatch, args):
    monkeypatch.setattr(sys, "argv", ["skipwatch", *args])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    return exc.value.code


@pytest.mark.parametrize("args", [["no-such-command"], ["--no-such-flag"], []])
def test_usage_errors_exit_64(monkeypatch, capsys, args):
    assert _run_main(monkeypatch, args) == ExitCode.USAGE
    assert capsys.readouterr().err.strip()


@pytest.mark.parametrize("args", [["--version"], ["--help"]])
def test_version_and_help_exit_0(monkeypatch, capsys, args):
    assert _run_main(monkeypatch, args) == 0
    assert capsys.readouterr().out.strip()


def test_main_keeps_command_exit_codes(monkeypatch, capsys):
    app = typer.Typer()

    @app.command()
    def boom():
        cli.run_command(
            lambda: (_ for _ in ()).throw(SkipwatchError(ExitCode.TARGET_EXISTS, "already there"))
        )

    monkeypatch.setattr(cli, "app", app)
    assert _run_main(monkeypatch, []) == ExitCode.TARGET_EXISTS
    assert "already there" in capsys.readouterr().err
