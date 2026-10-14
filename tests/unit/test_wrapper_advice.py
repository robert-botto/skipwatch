"""scripts/skipwatch: the exit-78 advice syncs with the wrapper's own flags (M6F-FR1 minor 7)."""

import sys

import pytest

from tests.unit.test_wrapper import SYSTEM_PATH, fake_uv, make_plugin, run

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX sh wrapper")


def _advice(stderr: str) -> str:
    lines = stderr.splitlines()
    return lines[lines.index(next(x for x in lines if "Run this once" in x)) + 1].strip()


@pytest.mark.parametrize("git", [False, True])
def test_exit_78_advice_uses_the_wrappers_sync_flags(tmp_path, git):
    root = make_plugin(tmp_path, venv=False)
    if git:
        (root / ".git").mkdir()
    bin_dir, log = fake_uv(tmp_path, ok=False)
    r = run(root, "doctor", path=f"{bin_dir}:{SYSTEM_PATH}")
    assert r.returncode == 78
    ran = log.read_text().split("\n")[0]  # the wrapper's own sync: "sync <flags> --project <root>"
    flags = ran.split(" --project ")[0].removeprefix("sync ")
    # an exact sync would uninstall an extra the user added; --no-dev only without .git
    assert _advice(r.stderr) == f'uv sync {flags} --project "{root}"'
    assert "--inexact" in flags and ("--no-dev" in flags) is not git
