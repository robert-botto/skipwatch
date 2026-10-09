import json
import os
import time
from datetime import datetime

from typer.testing import CliRunner

from skipwatch.cache import cache_status, clear_cache
from skipwatch.cli import app
from skipwatch.models import CacheResult


def _age(path, days):
    t = time.time() - days * 86400
    os.utime(path, (t, t))


def test_r_work_2_clear_removes_only_cache_and_old_work(sw_home):
    (sw_home / "cache/abc").mkdir(parents=True)
    old = sw_home / "work/old-20260901-000000"
    old.mkdir(parents=True)
    _age(old, 8)
    new = sw_home / "work/new-20261009-000000"
    new.mkdir(parents=True)
    keep = [sw_home / "config.toml", sw_home / "backups/x-1", sw_home / "staging/y"]
    keep[0].write_text("")
    keep[1].mkdir(parents=True)
    keep[2].mkdir(parents=True)
    r = clear_cache(sw_home, datetime.now())
    assert not (sw_home / "cache").exists() and not old.exists()
    assert new.exists() and all(p.exists() for p in keep)
    assert r.cleared and len(r.removed) == 2


def test_clear_on_empty_home_is_ok(sw_home):
    assert clear_cache(sw_home, datetime.now()).removed == []


def test_clear_keeps_files_in_work_and_six_day_old_folders(sw_home):
    recent = sw_home / "work/recent-20261003-000000"
    recent.mkdir(parents=True)
    _age(recent, 6)
    stray = sw_home / "work/notes.txt"
    stray.write_text("x")
    _age(stray, 30)
    r = clear_cache(sw_home, datetime.now())
    assert recent.exists() and stray.exists() and r.removed == []


def test_clear_never_follows_symlinks_out_of_home(sw_home, tmp_path):
    outside = tmp_path / "outside"
    (outside / "precious").mkdir(parents=True)
    (sw_home / "work").mkdir(parents=True)
    link = sw_home / "work/linked-20260901-000000"
    link.symlink_to(outside, target_is_directory=True)
    os.utime(link, (0, 0), follow_symlinks=False)
    (sw_home / "cache").mkdir()
    (sw_home / "cache/link").symlink_to(outside, target_is_directory=True)
    clear_cache(sw_home, datetime.now())
    assert (outside / "precious").exists()


def test_cache_status_counts(sw_home):
    (sw_home / "cache/a").mkdir(parents=True)
    (sw_home / "cache/b").mkdir()
    (sw_home / "work/w-20261009-000000").mkdir(parents=True)
    r = cache_status(sw_home)
    assert (r.cleared, r.cache_entries, r.work_folders, r.removed) == (False, 2, 1, [])


def test_cache_command_json_and_clear(sw_home):
    (sw_home / "cache/a").mkdir(parents=True)
    status = CliRunner().invoke(app, ["cache", "--json"])
    assert status.exit_code == 0
    assert CacheResult.model_validate_json(status.stdout).cache_entries == 1
    assert (sw_home / "cache/a").exists()
    cleared = CliRunner().invoke(app, ["cache", "--clear", "--json"])
    assert cleared.exit_code == 0
    assert json.loads(cleared.stdout)["cleared"] is True
    assert not (sw_home / "cache").exists()
    assert cleared.stderr
