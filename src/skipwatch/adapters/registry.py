"""Adapter registry: every module in skipwatch.adapters that defines PLATFORMS and ADAPTER.

New platforms are new files; nothing here changes when one is added.
"""

import importlib
import pkgutil
from functools import cache

from skipwatch import adapters
from skipwatch.adapters.base import Adapter


@cache
def _adapters() -> dict[str, Adapter]:
    found: dict[str, Adapter] = {}
    for info in sorted(pkgutil.iter_modules(adapters.__path__), key=lambda m: m.name):
        module = importlib.import_module(f"{adapters.__name__}.{info.name}")
        adapter = getattr(module, "ADAPTER", None)
        platforms = getattr(module, "PLATFORMS", None)
        if adapter is None or platforms is None:
            continue
        for platform in platforms:
            if platform in found:
                raise RuntimeError(f"platform {platform} is registered twice ({info.name})")
            found[platform] = adapter
    return found


def adapter_for(platform: str) -> Adapter | None:
    return _adapters().get(platform)


def all_platforms() -> set[str]:
    return set(_adapters())
