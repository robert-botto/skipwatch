"""Transcription from a captions file copied in by ingest (8.4, R-TR-1)."""

from pathlib import PurePath

from skipwatch.captions import language_from_name, parse_file
from skipwatch.models import IngestBundle, Transcript
from skipwatch.workdir import WorkDir, read_model


class CaptionsBackend:
    name = "captions"
    cloud = False
    auto_rank: int | None = 0

    def available(self, bundle: IngestBundle) -> bool:
        return bool(bundle.context.captions_available and bundle.context.captions_path)

    def missing_hint(self) -> str:
        return "no captions sidecar or platform captions"

    def transcribe(self, work: WorkDir, model: str | None) -> Transcript:
        bundle = read_model(work.file("ingest.json"), IngestBundle)
        captions_path = bundle.context.captions_path
        assert captions_path is not None, "transcribe() called on an unavailable backend"
        sidecar = work.path / captions_path
        media_stem = PurePath(bundle.source.path or "").stem
        language = bundle.context.captions_lang  # set by URL adapters (M2-B)
        if language is None and media_stem:
            language = language_from_name(sidecar.name, media_stem)
        return Transcript(
            origin="captions",
            model=None,
            language=language,
            segments=parse_file(sidecar),
        )


BACKENDS = (CaptionsBackend(),)
