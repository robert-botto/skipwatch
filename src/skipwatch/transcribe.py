"""Transcribe stage: pick a backend, write timed transcript.json, flag silence (8.4)."""

import os

from skipwatch.doctor import _extra_command  # one source for install advice (`--inexact`)
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import IngestBundle, Transcript
from skipwatch.providers.base import TranscriptionBackend
from skipwatch.providers.transcribe_captions import CaptionsBackend
from skipwatch.workdir import WorkDir, read_model, run_stage, write_model

LATER_BACKENDS = ("mlx", "faster", "openai", "groq", "deepgram")
SILENT_WPM = 20


def select_backend(requested: str, bundle: IngestBundle) -> TranscriptionBackend:
    captions = CaptionsBackend(bundle)
    if requested == "auto":
        if captions.available():
            return captions
        command = _extra_command(os.environ.get("CLAUDE_PLUGIN_ROOT"), "whisper")
        raise SkipwatchError(
            ExitCode.MISSING_DEPENDENCY,
            f"no captions and no Whisper backend; install one: {command}",
        )
    if requested == "captions":
        if captions.available():
            return captions
        raise SkipwatchError(ExitCode.NO_CONTENT, "no captions sidecar was found at ingest")
    if requested in LATER_BACKENDS:
        raise SkipwatchError(
            ExitCode.MISSING_DEPENDENCY, f"the {requested} backend arrives in M2; use captions"
        )
    raise SkipwatchError(ExitCode.USAGE, f"unknown backend {requested}")


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
