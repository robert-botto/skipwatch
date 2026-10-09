"""Provider protocols. Only TranscriptionBackend is used in M1; the rest are seams for M2+."""

from pathlib import Path
from typing import Protocol

from skipwatch.models import IngestBundle, Transcript
from skipwatch.workdir import WorkDir


class ContentProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    def fetch(self, url: str, work: WorkDir) -> IngestBundle: ...


class TranscriptionBackend(Protocol):
    name: str

    def available(self) -> bool: ...

    def transcribe(self, work: WorkDir, model: str | None) -> Transcript: ...


class ExportProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    def export(self, skill_dir: Path) -> None: ...


class IndexProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    def index(self, skill_dir: Path) -> None: ...
