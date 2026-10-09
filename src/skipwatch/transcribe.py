"""Transcribe stage: pick a backend, write timed transcript.json, flag silence (8.4)."""

import os
from typing import get_args

from skipwatch.doctor import extra_command, is_apple_silicon  # one source for install advice
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import IngestBundle, TranscribeConfig, Transcript
from skipwatch.providers.base import TranscriptionBackend
from skipwatch.providers.registry import transcription_backends
from skipwatch.workdir import WorkDir, read_model, run_stage, write_model

KNOWN_BACKENDS = frozenset(get_args(TranscribeConfig.model_fields["backend"].annotation)) - {"auto"}
SILENT_WPM = 20


def _whisper_hint() -> str:
    extra = "mlx" if is_apple_silicon() else "whisper"
    return extra_command(os.environ.get("CLAUDE_PLUGIN_ROOT"), extra)


def select_backend(requested: str, bundle: IngestBundle) -> TranscriptionBackend:
    """auto: the available backend with the lowest auto_rank; cloud never (R-TR-2)."""
    backends = transcription_backends()
    if requested == "auto":
        ranked = sorted(
            (b for b in backends.values() if not b.cloud and b.auto_rank is not None),
            key=lambda b: (b.auto_rank, b.name),
        )
        chosen = next((b for b in ranked if b.available(bundle)), None)
        if chosen is not None:
            return chosen
        raise SkipwatchError(
            ExitCode.MISSING_DEPENDENCY,
            f"no captions and no Whisper backend; install one: {_whisper_hint()}",
        )
    backend = backends.get(requested)
    if backend is None:
        if requested in KNOWN_BACKENDS:
            raise SkipwatchError(
                ExitCode.MISSING_DEPENDENCY, f"backend {requested} is not installed in this build"
            )
        raise SkipwatchError(ExitCode.USAGE, f"unknown backend {requested}")
    if backend.available(bundle):
        return backend
    if requested == "captions":
        raise SkipwatchError(ExitCode.NO_CONTENT, "no captions sidecar was found at ingest")
    raise SkipwatchError(
        ExitCode.MISSING_DEPENDENCY,
        f"backend {requested} is not available: {backend.missing_hint()}",
    )


def _word_count(t: Transcript) -> int:
    return sum(len(s.text.split()) for s in t.segments)


def mark_silence(t: Transcript, duration_s: float | None) -> Transcript:
    """silent when under 20 words per minute of audio; duration falls back to the last end."""
    duration = duration_s or (t.segments[-1].end if t.segments else 0.0)
    if duration <= 0:
        return t.model_copy(update={"silent": _word_count(t) == 0})
    wpm = _word_count(t) / (duration / 60)
    return t.model_copy(update={"silent": wpm < SILENT_WPM})


def run_transcribe(work: WorkDir, backend: str, model: str | None) -> Transcript:
    ingest_json = work.file("ingest.json")
    if not ingest_json.exists():
        raise SkipwatchError(ExitCode.NO_CONTENT, f"no ingest.json in {work.path}; run ingest")
    bundle = read_model(ingest_json, IngestBundle)

    def body() -> Transcript:
        chosen = select_backend(backend, bundle)
        transcript = chosen.transcribe(work, model)
        if not transcript.segments:
            # R-TR-1: never write a transcript without timed segments.
            raise SkipwatchError(ExitCode.NO_CONTENT, f"{chosen.name} produced no timed segments")
        transcript = mark_silence(transcript, bundle.source.duration_s)
        write_model(work.file("transcript.json"), transcript)
        return transcript

    return run_stage(work, "transcribe", body)
