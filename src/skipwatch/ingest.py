"""Ingest stage: detect the source, run its adapter, write source/ingest/calls JSON (8.3).

Adapters come from adapters/registry. Optional content providers (treg, M4) enrich every
bundle and supply media when the free route fails.
"""

import os
import re
from collections.abc import Callable
from pathlib import Path

from skipwatch import runcache
from skipwatch.adapters.base import DownloadFailed, IngestOptions, NoMediaError
from skipwatch.adapters.registry import adapter_for
from skipwatch.config import load_config
from skipwatch.detect import Detected, detect
from skipwatch.doctor import ytdlp_upgrade_command
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import (
    CallsFile,
    Config,
    IngestBundle,
    ProviderCall,
    Route,
    SourceFile,
    SourceInfo,
)
from skipwatch.providers.base import ContentProvider
from skipwatch.providers.registry import content_providers
from skipwatch.workdir import WorkDir, run_stage, write_model

# YouTube's CDN answers 403 or 429 intermittently; content_free has already retried once.
TRANSIENT_HTTP = re.compile(r"HTTP Error (403|429)|connection reset", re.IGNORECASE)


def _config_enabled(provider: ContentProvider, cfg: Config) -> bool:
    settings = getattr(cfg.providers, provider.name, None)
    return getattr(settings, "enabled", "auto") is not False


def enabled_providers(opts: IngestOptions, cfg: Config) -> list[ContentProvider]:
    """[] for --provider free; the named provider or exit 8; under auto every usable one."""
    if opts.provider == "free":
        return []
    registered = content_providers()
    if opts.provider == "auto":
        return [p for p in registered if _config_enabled(p, cfg) and p.available()]
    chosen = next((p for p in registered if p.name == opts.provider), None)
    if chosen is None or not chosen.available():
        raise SkipwatchError(
            ExitCode.MISSING_DEPENDENCY,
            f"{opts.provider} is not installed or not logged in: run `{opts.provider} login`",
        )
    return [chosen]


def _media_fallback(
    detected: Detected,
    work: WorkDir,
    opts: IngestOptions,
    providers: list[ContentProvider],
    failed: DownloadFailed,
) -> IngestBundle:
    attempts = list(failed.attempts)
    bundle = failed.bundle or IngestBundle(
        source=SourceInfo(kind="video", platform=detected.platform, url=detected.value),
        route=Route(context="free"),
    )
    for provider in providers:
        media = provider.fetch_media(bundle, work, opts)
        if media is not None:
            route = bundle.route.model_copy(
                update={"media": provider.name, "fallbacks": [*bundle.route.fallbacks, *attempts]}
            )
            return bundle.model_copy(update={"media": media, "route": route})
        attempts.append(f"{provider.name}.fetch_media: no media")
    upgrade = ytdlp_upgrade_command(os.environ.get("CLAUDE_PLUGIN_ROOT"))
    hint = f"Try: {upgrade}, or --cookies-from-browser <browser>, or the content is private."
    if any(TRANSIENT_HTTP.search(a) for a in attempts):
        hint = (
            "A 403 can be transient (it already failed twice in a row here): run the same "
            f"command again first. If it fails again, {hint[0].lower()}{hint[1:]}"
        )
    raise SkipwatchError(
        ExitCode.DOWNLOAD_FAILED,
        f"could not download {detected.value}: {'; '.join(attempts)}. {hint}",
    )


def _finish(
    providers: list[ContentProvider], work: WorkDir, bundle: IngestBundle | None
) -> tuple[IngestBundle | None, list[ProviderCall]]:
    """Every provider's end-of-run hook. A fresh bundle gets each provider's calls as that
    provider's entries in provider_calls; the calls are also returned, for calls.json when the
    run ends on a cache hit or an error."""
    billed: list[ProviderCall] = []
    for provider in providers:
        finish = getattr(provider, "finish", None)
        calls = list(finish(work, bundle)) if finish is not None else []
        billed += calls
        if calls and bundle is not None and not bundle.from_cache:
            others = [c for c in bundle.provider_calls if c.provider != provider.name]
            bundle = bundle.model_copy(update={"provider_calls": [*others, *calls]})
    return bundle, billed


def _record(work: WorkDir, calls: list[ProviderCall]) -> None:
    """calls.json for a run that ends without a fresh bundle: what it billed, nothing else."""
    write_model(work.file("calls.json"), CallsFile(calls=calls))


CacheLookup = Callable[[IngestBundle, list[ContentProvider], IngestOptions], IngestBundle | None]


def _build(
    detected: Detected,
    work: WorkDir,
    opts: IngestOptions,
    cfg: Config,
    cached: CacheLookup | None = None,
) -> IngestBundle:
    adapter = adapter_for(detected.platform)
    if adapter is None:
        raise SkipwatchError(ExitCode.UNSUPPORTED_SOURCE, f"no adapter for {detected.platform}")
    # A local file never consults content providers: no network call for the user's own file.
    providers = [] if detected.platform == "local" else enabled_providers(opts, cfg)
    try:
        bundle = _build_with(providers, adapter, detected, work, opts, cached)
    except Exception:
        # whatever ended the run, money already spent is logged and reviewed
        _, billed = _finish(providers, work, None)
        if billed:
            _record(work, billed)
        raise
    finished, billed = _finish(providers, work, bundle)
    if finished is None:  # unreachable: a bundle in gives a bundle out
        raise SkipwatchError(ExitCode.INTERNAL_ERROR, "a content provider lost the bundle")
    if finished.from_cache:
        _record(work, billed)
    return finished


def _build_with(
    providers: list[ContentProvider],
    adapter,
    detected: Detected,
    work: WorkDir,
    opts: IngestOptions,
    cached: CacheLookup | None,
) -> IngestBundle:
    try:
        bundle = adapter.build(detected, work, opts)
    except NoMediaError as exc:
        text = adapter_for("text")
        if text is None:
            raise SkipwatchError(
                ExitCode.NO_CONTENT, f"{exc.url} has no video: {exc.reason}"
            ) from exc
        bundle = text.build(detected, work, opts)
    except DownloadFailed as exc:
        bundle = _media_fallback(detected, work, opts, providers, exc)
    # R-TR-3: a fresh cached ingest replaces enrichment (treg is never billed twice); media
    # above was still fetched, frames need it.
    hit = cached(bundle, providers, opts) if cached is not None else None
    if hit is not None:
        return hit
    for provider in providers:
        bundle = provider.enrich(bundle, work, opts)
    return bundle


def build_bundle(
    value: str, work: WorkDir, opts: IngestOptions, cfg: Config, cwd: Path | None = None
) -> IngestBundle:
    return _build(detect(value, cwd), work, opts, cfg)


def _write(work: WorkDir, bundle: IngestBundle) -> None:
    src = bundle.source
    write_model(
        work.file("source.json"),
        SourceFile(
            kind=src.kind,
            platform=src.platform,
            url=src.url,
            canonical_url=src.canonical_url,
            path=src.path,
        ),
    )
    # a cache hit: _build already wrote what this run billed (often nothing), never the
    # cached calls, so cost is never counted twice
    if not bundle.from_cache:
        write_model(work.file("calls.json"), CallsFile(calls=bundle.provider_calls))
    write_model(work.file("ingest.json"), bundle)


def cache_lookup(
    bundle: IngestBundle, providers: list[ContentProvider], opts: IngestOptions
) -> IngestBundle | None:
    """The run cache, keyed the one way every caller uses (ingest and treg's text-only X): the
    source, cookies and the sorted names of the enabled providers (runcache.cache_key)."""
    cookies = opts.cookies_from_browser is not None
    return runcache.cached_ingest(bundle, [p.name for p in providers], cookies)


def run_ingest(
    value: str,
    work: WorkDir,
    opts: IngestOptions,
    cwd: Path | None = None,
    cfg: Config | None = None,
) -> IngestBundle:
    work.ensure()
    detected = run_stage(work, "detect", lambda: detect(value, cwd))

    def body() -> IngestBundle:
        cookies = opts.cookies_from_browser is not None
        enabled: list[str] = []  # the providers _build settled on, for the cache key

        def lookup(
            bundle: IngestBundle, providers: list[ContentProvider], opts: IngestOptions
        ) -> IngestBundle | None:
            enabled[:] = [p.name for p in providers]
            return cache_lookup(bundle, providers, opts)

        bundle = _build(detected, work, opts, cfg or load_config(), lookup)
        _write(work, bundle)
        runcache.remember_ingest(bundle, work.file("ingest.json"), cookies, enabled)
        return bundle

    return run_stage(work, "ingest", body)
