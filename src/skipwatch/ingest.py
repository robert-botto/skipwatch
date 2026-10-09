"""Ingest stage: detect the source, run its adapter, write source/ingest/calls JSON (8.3)."""

from pathlib import Path

from skipwatch.adapters.base import Adapter, IngestOptions
from skipwatch.adapters.localfile import LocalFileAdapter
from skipwatch.detect import Detected, detect
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import CallsFile, IngestBundle, SourceFile
from skipwatch.workdir import WorkDir, run_stage, write_model


def choose_adapter(detected: Detected) -> Adapter:
    if detected.platform == "local":
        return LocalFileAdapter()
    raise SkipwatchError(
        ExitCode.UNSUPPORTED_SOURCE,
        f"URL sources arrive in M2 ({detected.platform}); pass a local video or audio file",
    )


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
    value: str, work: WorkDir, opts: IngestOptions, cwd: Path | None = None
) -> IngestBundle:
    work.ensure()
    detected = run_stage(work, "detect", lambda: detect(value, cwd))

    def body() -> IngestBundle:
        bundle = choose_adapter(detected).build(detected, work, opts)
        _write(work, bundle)
        return bundle

    return run_stage(work, "ingest", body)
