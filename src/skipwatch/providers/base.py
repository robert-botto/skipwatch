"""Provider protocols. Content providers and transcription backends register through
providers/registry.py; export and index providers are seams for M5+."""

from pathlib import Path
from typing import Protocol

from skipwatch.adapters.base import IngestOptions
from skipwatch.models import IngestBundle, MediaInfo, ProviderCall, Transcript
from skipwatch.workdir import WorkDir


class ContentProvider(Protocol):
    name: str  # "treg"

    def available(self) -> bool:
        """Installed and logged in; may do one cheap check."""
        ...

    def enrich(self, bundle: IngestBundle, work: WorkDir, opts: IngestOptions) -> IngestBundle: ...

    def fetch_media(
        self, bundle: IngestBundle, work: WorkDir, opts: IngestOptions
    ) -> MediaInfo | None: ...

    def finish(self, work: WorkDir, bundle: IngestBundle | None) -> list[ProviderCall]:
        """End of the ingest run, on every exit path (bundle None when it failed): the calls
        this provider made in the run, reviewed, and its per-run state dropped. Optional:
        ingest treats a provider without it as having made no calls of its own."""
        return []


class TranscriptionBackend(Protocol):
    name: str  # "captions" | "mlx" | "faster" | "openai" | "groq" | "deepgram"
    cloud: bool  # True only for openai, groq, deepgram
    auto_rank: int | None  # order under auto: captions 0, mlx 1, faster 2; cloud None

    def available(self, bundle: IngestBundle) -> bool: ...

    def transcribe(self, work: WorkDir, model: str | None) -> Transcript: ...

    def missing_hint(self) -> str:
        """Install command or env var to set, for exit 8."""
        ...


class ExportProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    def export(self, skill_dir: Path) -> None: ...


class IndexProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    def index(self, skill_dir: Path) -> None: ...
