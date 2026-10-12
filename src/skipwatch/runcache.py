"""Run cache (R-TR-3, plan issue 6): ingest.json and transcript.json reused for 7 days.

`$SKIPWATCH_HOME/cache/<key>/` holds the cached files and `entry.json` (CacheEntry). The key
is `sha256(canonical_url or url)[:16]`, or `sha256("<abs path>|<size>|<mtime_ns>")[:16]` for a
local file. An ingest entry's key also names the content providers enabled for it, so an
entry only ever serves a run that would have asked the same providers. A run whose media or
context was fetched with browser cookies uses a separate key (`|cookies` appended), so private
content never reaches a cookieless run (and an entry flagged `fetched_with_cookies` is refused
there anyway). Media is never cached: frames need it, so a cached ingest still downloads.

An entry is fresh for 7 days from its first store; later stores add files but never extend
that. A stale or corrupt entry is a miss, and the next store replaces it whole. The cache is
best effort: a file that will not read is a miss, a store that fails is one stderr line.
"""

import hashlib
import os
import shutil
import tempfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from skipwatch.config import skipwatch_home
from skipwatch.models import CacheEntry, IngestBundle, ProviderCall, SourceInfo, Transcript
from skipwatch.output import progress
from skipwatch.workdir import read_model

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


def cache_key(
    source: SourceInfo, cookies: bool = False, providers: Sequence[str] = ()
) -> str | None:
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
    if cookies:
        raw += "|cookies"
    if providers:
        raw += "|providers=" + ",".join(sorted(set(providers)))
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


def _replace(folder: Path, name: str, write: Callable[[Path], object]) -> None:
    """Write through a unique temp file in the folder, then os.replace (safe with two runs)."""
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=f".{name}.", suffix=".tmp")
    os.close(fd)
    try:
        write(Path(tmp))
        os.replace(tmp, folder / name)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


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
        _replace(folder, name, lambda tmp, src=src: shutil.copyfile(src, tmp))
    kept = entry.files if entry else []
    new = CacheEntry(
        key=key,
        source=source,
        created_at=entry.created_at if entry else _iso(now),
        files=sorted({*kept, *files}),
    )
    text = new.model_dump_json(by_alias=True, indent=2) + "\n"
    _replace(folder, ENTRY, lambda tmp: tmp.write_text(text, encoding="utf-8"))
    return new


def _read_entry(key: str | None, name: str, cls: type[M]) -> tuple[M, CacheEntry] | None:
    """(model, entry) for a fresh entry holding a valid `name`."""
    if key is None:
        return None
    folder = _folder(skipwatch_home(), key)
    entry = _fresh_entry(folder, utcnow())
    if entry is None or name not in entry.files:
        return None
    try:
        model = read_model(folder / name, cls)
    except (OSError, ValidationError):  # removed or rewritten by another run: a miss
        return None
    return model, entry


def _read_cached(key: str | None, name: str, cls: type[M]) -> tuple[M, int] | None:
    """(model, entry age in whole hours) for a fresh entry holding a valid `name`."""
    found = _read_entry(key, name, cls)
    if found is None:
        return None
    model, entry = found
    age = _aware(utcnow()) - _aware(datetime.fromisoformat(entry.created_at))
    return model, int(age.total_seconds() // 3600)


def _remember(key: str | None, source: SourceInfo, name: str, path: Path) -> None:
    if key is None:
        return
    label = source.canonical_url or source.url or source.path or ""
    try:
        store(skipwatch_home(), key, label, {name: path}, utcnow())
    except OSError as exc:
        progress(f"Cache: could not store {name}: {exc.strerror or exc}")


LINK_OPS_PREFIX = "link."


def _failed(call: ProviderCall) -> bool:
    """A provider failure that keeps a run out of the cache. A dead link (link.get,
    link.resolve) is the post's content, not a failure: caching around it is what keeps a rerun
    from paying the providers again (R-TR-3)."""
    return not call.ok and not call.op.startswith(LINK_OPS_PREFIX) and call.provider != "links"


def remember_ingest(
    bundle: IngestBundle, path: Path, cookies: bool, providers: Sequence[str]
) -> None:
    """Store a freshly built ingest.json under the providers that enriched it; never one served
    from the cache or with a failed provider call (the next run should ask that provider again;
    a dead link is not a failure). Never fails the stage."""
    if bundle.from_cache or any(_failed(c) for c in bundle.provider_calls):
        return
    cookies = cookies or bundle.fetched_with_cookies
    _remember(cache_key(bundle.source, cookies, providers), bundle.source, "ingest.json", path)


def remember_transcript(bundle: IngestBundle, path: Path) -> None:
    key = cache_key(bundle.source, bundle.fetched_with_cookies)
    _remember(key, bundle.source, "transcript.json", path)


def cached_ingest(fresh: IngestBundle, providers: list[str], cookies: bool) -> IngestBundle | None:
    """The fresh bundle with cached context, source, hint and provider calls, or None.

    The key names the providers enabled now, so the entry was enriched by exactly these; one
    that made no call had nothing to add (treg on a captioned YouTube video). Providers decide
    on captions, so a change in captions since then is a miss. An entry with a failed call is
    never served. Captions stay this run's: they live in this work folder. A cookie-fetched
    entry is never served to a cookieless run.
    """
    if not providers:
        return None
    cookies = cookies or fresh.fetched_with_cookies
    key = cache_key(fresh.source, cookies, providers)
    found = _read_entry(key, "ingest.json", IngestBundle)
    if found is None:
        return None
    cached, entry = found
    if cached.fetched_with_cookies and not cookies:
        return None
    if any(_failed(c) for c in cached.provider_calls):
        return None
    if cached.context.captions_available != fresh.context.captions_available:
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
            "fetched_with_cookies": fresh.fetched_with_cookies or cached.fetched_with_cookies,
            "from_cache": True,
            "cached_at": entry.created_at,
        }
    )


def cached_transcript(
    bundle: IngestBundle, backend: str, model: str | None
) -> tuple[Transcript, int] | None:
    """(transcript, age in hours) when a fresh one matches the backend (any under auto)."""
    key = cache_key(bundle.source, bundle.fetched_with_cookies)
    found = _read_cached(key, "transcript.json", Transcript)
    if found is None:
        return None
    transcript = found[0]
    if backend != "auto" and BACKEND_ORIGINS.get(backend) != transcript.origin:
        return None
    if model is not None and transcript.model != model:
        return None
    return found
