"""Provider registry: content providers (`content_*.py` defining PROVIDER), transcription
backends (`transcribe_*.py` defining BACKENDS) and export providers (`export_*.py` defining
PROVIDER).

content_free is the shared yt-dlp library the adapters use, not a provider, so it is skipped.
Backend modules import heavy libraries (faster_whisper, mlx_whisper) lazily inside
transcribe(). A module that still fails to import (any exception) is reported on stderr and
skipped, so one broken backend never takes captions down with it.
"""

import importlib
import pkgutil
from functools import cache
from types import ModuleType

from skipwatch import providers
from skipwatch.output import progress
from skipwatch.providers.base import ContentProvider, ExportProvider, TranscriptionBackend

NOT_A_PROVIDER = {"content_free"}


def _modules(prefix: str) -> list[ModuleType]:
    names = sorted(
        info.name
        for info in pkgutil.iter_modules(providers.__path__)
        if info.name.startswith(prefix) and info.name not in NOT_A_PROVIDER
    )
    modules = []
    for name in names:
        try:
            modules.append(importlib.import_module(f"{providers.__name__}.{name}"))
        except Exception as exc:  # one broken backend must not take the others down
            progress(f"skipwatch: skipped provider module {name}: {exc}")
    return modules


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


@cache
def _export_providers() -> dict[str, ExportProvider]:
    found: dict[str, ExportProvider] = {}
    for module in _modules("export_"):
        provider = getattr(module, "PROVIDER", None)
        if provider is None:
            continue
        if provider.name in found:
            raise RuntimeError(f"export provider {provider.name} is registered twice")
        found[provider.name] = provider
    return dict(sorted(found.items()))


def content_providers() -> list[ContentProvider]:
    """Every registered content provider, sorted by name."""
    return list(_content_providers())


def transcription_backends() -> dict[str, TranscriptionBackend]:
    return dict(_backends())


def export_providers() -> dict[str, ExportProvider]:
    """Every registered export provider by name, sorted by name."""
    return dict(_export_providers())
