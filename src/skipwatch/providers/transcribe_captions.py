"""Transcription from a captions sidecar copied in by ingest (8.4, R-TR-1)."""

from pathlib import PurePath

from skipwatch.captions import language_from_name, parse_file
from skipwatch.models import IngestBundle, Transcript
from skipwatch.workdir import WorkDir


class CaptionsBackend:
    name = "captions"

    def __init__(self, bundle: IngestBundle):
        self.bundle = bundle

    def available(self) -> bool:
        return bool(self.bundle.context.captions_available and self.bundle.context.captions_path)

    def transcribe(self, work: WorkDir, model: str | None) -> Transcript:
        captions_path = self.bundle.context.captions_path
        assert captions_path is not None, "transcribe() called on an unavailable backend"
        sidecar = work.path / captions_path
        media_stem = PurePath(self.bundle.source.path or "").stem
        return Transcript(
            origin="captions",
            model=None,
            language=language_from_name(sidecar.name, media_stem) if media_stem else None,
            segments=parse_file(sidecar),
        )
