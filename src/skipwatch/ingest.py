"""Ingest stage: detect the source, run its adapter, write source/ingest/calls JSON (8.3).

Adapters come from adapters/registry. Optional content providers (treg, M4) enrich every
bundle and supply media when the free route fails.
"""

import os
from pathlib import Path

from skipwatch.adapters.base import DownloadFailed, IngestOptions, NoMediaError
from skipwatch.adapters.registry import adapter_for
from skipwatch.config import load_config
from skipwatch.detect import Detected, detect
from skipwatch.doctor import ytdlp_upgrade_command
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import CallsFile, Config, IngestBundle, Route, SourceFile, SourceInfo
from skipwatch.providers.base import ContentProvider
from skipwatch.providers.registry import content_providers
from skipwatch.workdir import WorkDir, run_stage, write_model


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
    raise SkipwatchError(
        ExitCode.DOWNLOAD_FAILED,
        f"could not download {detected.value}: {'; '.join(attempts)}. "
        f"Try: {upgrade}, or --cookies-from-browser <browser>, or the content is private.",
    )


def _build(detected: Detected, work: WorkDir, opts: IngestOptions, cfg: Config) -> IngestBundle:
    adapter = adapter_for(detected.platform)
    if adapter is None:
        raise SkipwatchError(ExitCode.UNSUPPORTED_SOURCE, f"no adapter for {detected.platform}")
    providers = enabled_providers(opts, cfg)
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
    write_model(work.file("calls.json"), CallsFile(calls=bundle.provider_calls))
    write_model(work.file("ingest.json"), bundle)


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
        bundle = _build(detected, work, opts, cfg or load_config())
        _write(work, bundle)
        return bundle

    return run_stage(work, "ingest", body)
