"""Provider registry: content providers (`content_*.py` defining PROVIDER) and transcription
backends (`transcribe_*.py` defining BACKENDS).

content_free is the shared yt-dlp library the adapters use, not a provider, so it is skipped.
Backend modules import heavy libraries (faster_whisper, mlx_whisper) lazily inside
transcribe(), so a missing extra never breaks this import.
"""

import importlib
import pkgutil
from functools import cache
from types import ModuleType

from skipwatch import providers
from skipwatch.providers.base import ContentProvider, TranscriptionBackend

NOT_A_PROVIDER = {"content_free"}


def _modules(prefix: str) -> list[ModuleType]:
    names = sorted(
        info.name
        for info in pkgutil.iter_modules(providers.__path__)
        if info.name.startswith(prefix) and info.name not in NOT_A_PROVIDER
    )
    return [importlib.import_module(f"{providers.__name__}.{name}") for name in names]


@cache
def _content_providers() -> tuple[ContentProvider, ...]:
    found = [getattr(m, "PROVIDER", None) for m in _modules("content_")]
    return tuple(sorted((p for p in found if p is not None), key=lambda p: p.name))


@cache
def _backends() -> dict[str, TranscriptionBackend]:
    found: dict[str, TranscriptionBackend] = {}
    for module in _modules("transcribe_"):
        for backend in getattr(module, "BACKENDS", ()):
            if backend.name in found:
                raise RuntimeError(f"backend {backend.name} is registered twice")
            found[backend.name] = backend
    return found


def content_providers() -> list[ContentProvider]:
    """Every registered content provider, sorted by name."""
    return list(_content_providers())


def transcription_backends() -> dict[str, TranscriptionBackend]:
    return dict(_backends())
