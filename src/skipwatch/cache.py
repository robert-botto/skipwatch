"""`skipwatch cache`: report and clear reusable data (R-WORK-2).

`--clear` removes `cache/` and work folders older than 7 days, nothing else. Symlinks are
unlinked, never followed, so nothing outside SKIPWATCH_HOME can be deleted.
"""

import shutil
from datetime import datetime, timedelta
from pathlib import Path

from skipwatch.models import CacheResult

WORK_MAX_AGE = timedelta(days=7)


def _dirs(folder: Path) -> list[Path]:
    if not folder.is_dir() or folder.is_symlink():
        return []
    return sorted(p for p in folder.iterdir() if p.is_dir() or p.is_symlink())


def cache_status(home: Path) -> CacheResult:
    return CacheResult(
        cleared=False,
        cache_entries=len(_dirs(home / "cache")),
        work_folders=len(_dirs(home / "work")),
    )


def _remove(path: Path) -> None:
    if path.is_symlink():
        path.unlink()
    else:
        shutil.rmtree(path)


def clear_cache(home: Path, now: datetime) -> CacheResult:
    removed: list[Path] = []
    cache = home / "cache"
    if cache.exists() or cache.is_symlink():
        _remove(cache)
        removed.append(cache)
    cutoff = (now - WORK_MAX_AGE).timestamp()
    for folder in _dirs(home / "work"):
        if folder.lstat().st_mtime < cutoff:
            _remove(folder)
            removed.append(folder)
    after = cache_status(home)
    return after.model_copy(update={"cleared": True, "removed": [str(p) for p in removed]})
