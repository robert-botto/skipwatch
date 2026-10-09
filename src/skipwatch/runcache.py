"""Run cache (R-TR-3, plan issue 6): ingest.json and transcript.json reused for 7 days.

`$SKIPWATCH_HOME/cache/<key>/` holds the cached files and `entry.json` (CacheEntry). The key
is `sha256(canonical_url or url)[:16]`, or `sha256("<abs path>|<size>|<mtime_ns>")[:16]` for a
local file. Media is never cached: frames need it, so a cached ingest still downloads.

An entry is fresh for 7 days from its first store; later stores add files but never extend
that. A stale or corrupt entry is a miss, and the next store replaces it whole. The cache is
best effort: a file that will not read is a miss, a store that fails is one stderr line.
"""

import hashlib
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from skipwatch.config import skipwatch_home
from skipwatch.models import CacheEntry, IngestBundle, SourceInfo, Transcript
from skipwatch.output import progress
from skipwatch.workdir import read_model, write_model

M = TypeVar("M", bound=BaseModel)

MAX_AGE = timedelta(days=7)
ENTRY = "entry.json"

# transcribe --backend name -> Transcript.origin it produces
BACKEND_ORIGINS = {
    "captions": "captions",
    "mlx": "mlx-whisper",
    "faster": "faster-whisper",
    "openai": "openai",
    "groq": "groq",
    "deepgram": "deepgram",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(when: datetime) -> str:
    return _aware(when).isoformat(timespec="seconds").replace("+00:00", "Z")


def _aware(when: datetime) -> datetime:
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def cache_key(source: SourceInfo) -> str | None:
    """None when the source has no stable identity (no URL, or a local file that is gone)."""
    url = source.canonical_url or source.url
    if url:
        raw = url
    elif source.path:
        path = Path(source.path).absolute()
        try:
            st = path.stat()
        except OSError:
            return None
        raw = f"{path}|{st.st_size}|{st.st_mtime_ns}"
    else:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _folder(home: Path, key: str) -> Path:
    return home / "cache" / key


def _fresh_entry(folder: Path, now: datetime) -> CacheEntry | None:
    try:
        entry = read_model(folder / ENTRY, CacheEntry)
        created = _aware(datetime.fromisoformat(entry.created_at))
    except (OSError, ValueError):  # ValidationError is a ValueError
        return None
    age = _aware(now) - created
    return entry if timedelta(0) <= age < MAX_AGE else None


def lookup(home: Path, key: str, name: str, now: datetime) -> Path | None:
    entry = _fresh_entry(_folder(home, key), now)
    if entry is None or name not in entry.files:
        return None
    path = _folder(home, key) / name
    return path if path.is_file() else None


def age_hours(home: Path, key: str, now: datetime) -> int:
    entry = read_model(_folder(home, key) / ENTRY, CacheEntry)
    age = _aware(now) - _aware(datetime.fromisoformat(entry.created_at))
    return int(age.total_seconds() // 3600)


def store(home: Path, key: str, source: str, files: dict[str, Path], now: datetime) -> CacheEntry:
    folder = _folder(home, key)
    entry = _fresh_entry(folder, now)
    if entry is None and (folder.exists() or folder.is_symlink()):
        # stale or corrupt: start over, so an old file never rides on a new created_at
        if folder.is_symlink() or not folder.is_dir():
            folder.unlink()
        else:
            shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name, src in files.items():
        tmp = folder / f"{name}.tmp"
        shutil.copyfile(src, tmp)
        os.replace(tmp, folder / name)
    kept = entry.files if entry else []
    new = CacheEntry(
        key=key,
        source=source,
        created_at=entry.created_at if entry else _iso(now),
        files=sorted({*kept, *files}),
    )
    write_model(folder / ENTRY, new)
    return new


def _read_cached(key: str | None, name: str, cls: type[M]) -> M | None:
    if key is None:
        return None
    path = lookup(skipwatch_home(), key, name, utcnow())
    if path is None:
        return None
    try:
        return read_model(path, cls)
    except (OSError, ValidationError):
        return None


def remember(source: SourceInfo, name: str, path: Path) -> None:
    """Store one written work file for this source; never fails the stage."""
    key = cache_key(source)
    if key is None:
        return
    try:
        store(
            skipwatch_home(),
            key,
            source.canonical_url or source.url or source.path or "",
            {name: path},
            utcnow(),
        )
    except OSError as exc:
        progress(f"Cache: could not store {name}: {exc.strerror or exc}")


def cached_ingest(fresh: IngestBundle, providers: list[str]) -> IngestBundle | None:
    """The fresh bundle with cached context, source, hint and provider calls, or None.

    Only a hit when every provider enabled now was used for the cached bundle, so turning a
    provider on within 7 days still asks it. Captions stay this run's: they live in this work
    folder.
    """
    if not providers:
        return None
    cached = _read_cached(cache_key(fresh.source), "ingest.json", IngestBundle)
    if cached is None or not set(providers) <= {c.provider for c in cached.provider_calls}:
        return None
    captions = {
        field: getattr(fresh.context, field)
        for field in ("captions_available", "captions_path", "captions_lang", "captions_kind")
    }
    return fresh.model_copy(
        update={
            "source": cached.source,
            "context": cached.context.model_copy(update=captions),
            "transcript_hint": cached.transcript_hint,
            "provider_calls": cached.provider_calls,
            "route": fresh.route.model_copy(update={"context": cached.route.context}),
            "from_cache": True,
        }
    )


def cached_transcript(
    source: SourceInfo, backend: str, model: str | None
) -> tuple[Transcript, int] | None:
    """(transcript, age in hours) when a fresh one matches the backend (any under auto)."""
    key = cache_key(source)
    transcript = _read_cached(key, "transcript.json", Transcript)
    if key is None or transcript is None:
        return None
    if backend != "auto" and BACKEND_ORIGINS.get(backend) != transcript.origin:
        return None
    if model is not None and transcript.model != model:
        return None
    return transcript, age_hours(skipwatch_home(), key, utcnow())
