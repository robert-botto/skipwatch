"""First run: doctor reports it once per home, and the skill prints the wordmark for it."""

from pathlib import Path

import pytest

from skipwatch import firstrun


def test_claim_is_true_once_per_home(tmp_path):
    home = tmp_path / ".skipwatch"
    assert firstrun.claim(home) is True
    assert firstrun.claim(home) is False
    assert (home / firstrun.MARKER).is_file()


def test_marker_symlink_is_not_followed(tmp_path):
    home = tmp_path / ".skipwatch"
    home.mkdir()
    target = tmp_path / "outside.txt"
    try:
        (home / firstrun.MARKER).symlink_to(target)
    except OSError:
        pytest.skip("symlinks need privilege here")
    assert firstrun.claim(home) is False  # a dangling link counts as present
    assert not target.exists()  # and is never followed to create its target
    target.write_text("keep", encoding="utf-8")
    assert firstrun.claim(home) is False
    assert target.read_text(encoding="utf-8") == "keep"


def test_unwritable_home_never_fails_or_repeats(tmp_path):
    home = tmp_path / ".skipwatch"
    home.write_text("a file, not a folder", encoding="utf-8")
    assert firstrun.claim(home) is False


def test_no_em_dash_in_first_run_sources():
    for path in (Path(firstrun.__file__), Path(__file__)):
        assert "\u2014" not in path.read_text(encoding="utf-8"), path
    assert "\u2014" not in firstrun.WELCOME
