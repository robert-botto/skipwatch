"""Shared by the local Whisper backends: audio in, timed segments with words out (R-TR-1)."""

from collections.abc import Iterable
from pathlib import Path

from skipwatch.audio import audio_duration, extract_audio
from skipwatch.models import IngestBundle, Segment, Word
from skipwatch.workdir import WorkDir, read_model


def has_media(bundle: IngestBundle) -> bool:
    # No audio track is not a missing dependency: extract_audio raises exit 7 for it.
    return bundle.media is not None


def wav_for(work: WorkDir) -> Path:
    return extract_audio(work, read_model(work.file("ingest.json"), IngestBundle))


def make_segment(start: float, end: float, text: str, words: Iterable[tuple[str, float, float]]):
    kept = [Word(w=w.strip(), s=max(0.0, s), e=max(0.0, e)) for w, s, e in words if w.strip()]
    return Segment(start=max(0.0, start), end=max(0.0, end), text=text.strip(), words=kept)


def or_silence(segments: list[Segment], wav: Path) -> list[Segment]:
    """No speech found: one empty segment over the whole audio, so silence detection marks the
    transcript silent (8.4) instead of the run failing for lack of timed segments."""
    if segments:
        return segments
    return [Segment(start=0.0, end=round(audio_duration(wav), 3), text="", words=[])]
