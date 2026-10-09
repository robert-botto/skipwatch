"""Pydantic models for every file SkipWatch writes (R-ARCH-2). schemas/ is generated from here."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def _tag(value: str) -> Any:
    return Field(default=value, alias="schema")


# ---- config.toml (7.7) ----
class InstallConfig(_Model):
    scope: Literal["user", "project"] = "user"


class FramesConfig(_Model):
    per_minute: int = Field(default=3, ge=1)
    max: int = Field(default=60, ge=1)


class TranscribeConfig(_Model):
    backend: Literal["auto", "captions", "mlx", "faster", "openai", "groq", "deepgram"] = "auto"
    model: str = ""


class TregConfig(_Model):
    enabled: Literal["auto", True, False] = "auto"


class ProvidersConfig(_Model):
    treg: TregConfig = TregConfig()


class StyleConfig(_Model):
    forbid: list[str] = ["em-dash"]


class Mem0Config(_Model):
    enabled: bool = False
    tag: str = "skipwatch"


class NotesConfig(_Model):
    enabled: bool = False
    folder: str = ""


class ExportsConfig(_Model):
    mem0: Mem0Config = Mem0Config()
    notes: NotesConfig = NotesConfig()


class Config(_Model):
    install: InstallConfig = InstallConfig()
    frames: FramesConfig = FramesConfig()
    transcribe: TranscribeConfig = TranscribeConfig()
    providers: ProvidersConfig = ProvidersConfig()
    style: StyleConfig = StyleConfig()
    exports: ExportsConfig = ExportsConfig()


# ---- ingest.json (7.1) ----
SourceKind = Literal["video", "audio", "text", "file"]


class SourceInfo(_Model):
    kind: SourceKind
    platform: str
    url: str | None = None
    canonical_url: str | None = None
    path: str | None = None
    author: str | None = None
    author_name: str | None = None
    title: str | None = None
    posted_at: str | None = None
    duration_s: float | None = None


class LinkContext(_Model):
    url: str
    title: str | None = None
    text: str = Field(default="", max_length=20_000)


class IngestContext(_Model):
    post_text: str | None = None
    thread: list[str] = []
    author_replies: list[str] = []
    links: list[LinkContext] = []
    captions_available: bool = False
    captions_path: str | None = None  # work-relative path of the copied sidecar (M1 localfile)


class MediaInfo(_Model):
    path: str
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    has_audio: bool = False


class TranscriptHint(_Model):
    origin: str = "none"
    text: str | None = None


class ProviderCall(_Model):
    provider: str
    op: str
    ok: bool
    cost_usd: float = 0
    ms: int = 0


class Route(_Model):
    context: str
    media: str | None = None
    fallbacks: list[str] = []


class IngestBundle(_Model):
    schema_: Literal["skipwatch/ingest/1"] = _tag("skipwatch/ingest/1")
    source: SourceInfo
    context: IngestContext = IngestContext()
    media: MediaInfo | None = None
    transcript_hint: TranscriptHint = TranscriptHint()
    provider_calls: list[ProviderCall] = []
    route: Route
    fetched_with_cookies: bool = False


# ---- transcript.json (7.2) ----
TranscriptOrigin = Literal[
    "captions", "mlx-whisper", "faster-whisper", "openai", "groq", "deepgram"
]


class Word(_Model):
    w: str
    s: float
    e: float


class Segment(_Model):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str
    words: list[Word] | None = None


class CrossCheck(_Model):
    origin: str
    text: str
    similarity: float | None = None


class Transcript(_Model):
    schema_: Literal["skipwatch/transcript/1"] = _tag("skipwatch/transcript/1")
    origin: TranscriptOrigin
    model: str | None = None
    language: str | None = None
    segments: list[Segment]
    cross_check: CrossCheck | None = None
    silent: bool = False


# ---- frames.json (7.3) ----
class Sampling(_Model):
    per_minute: int
    max: int
    dense: bool = False
    cue_terms: list[str] = []


class Frame(_Model):
    id: str = Field(pattern=r"^f\d{6}$")
    t: float = Field(ge=0)
    path: str
    reason: Literal["scene", "cue", "spread"]
    transcript_window: str = ""
    dhash: str = Field(pattern=r"^[0-9a-f]{16}$")


class FramesFile(_Model):
    schema_: Literal["skipwatch/frames/1"] = _tag("skipwatch/frames/1")
    sampling: Sampling
    frames: list[Frame]


# ---- batches.json and notes/batch-NN.json (7.4) ----
class Batch(_Model):
    id: int = Field(ge=1)
    frame_ids: list[str]
    notes_path: str


class BatchesFile(_Model):
    schema_: Literal["skipwatch/batches/1"] = _tag("skipwatch/batches/1")
    batches: list[Batch]


class VerbatimItem(_Model):
    kind: Literal["command", "code", "prompt", "setting", "ui_path", "url", "text"]
    text: str
    confidence: float = Field(ge=0, le=1)


class FrameNote(_Model):
    id: str
    t: float
    shows: Literal[
        "terminal", "code editor", "browser ui", "slide", "prompt box", "settings panel", "other"
    ]
    verbatim: list[VerbatimItem] = []
    illegible: list[str] = []
    new_since_previous: bool = True
    note: str = ""


class NotesFile(_Model):
    schema_: Literal["skipwatch/notes/1"] = _tag("skipwatch/notes/1")
    batch: int
    frames: list[FrameNote]


# ---- check-report.json (7.5) ----
CheckName = Literal["frontmatter", "structure", "provenance", "redaction", "safety", "style"]


class CheckItem(_Model):
    step: int | None = None
    msg: str
    fix: str | None = None


class SafetyFlag(_Model):
    step: int | None = None
    kind: str
    text: str
    severity: Literal["low", "medium", "high"]


class CheckResult(_Model):
    check: CheckName
    ok: bool
    items: list[CheckItem] = []
    flags: list[SafetyFlag] = []


class Counts(_Model):
    steps: int = 0
    spoken: int = 0
    on_screen: int = 0
    written: int = 0
    inferred: int = 0
    gaps: int = 0
    illegible: int = 0


class CheckReport(_Model):
    schema_: Literal["skipwatch/check/1"] = _tag("skipwatch/check/1")
    skill: str
    passed: bool
    results: list[CheckResult]
    counts: Counts


# ---- skipwatch.json (7.6) ----
class ManifestSource(_Model):
    url: str | None = None
    canonical_url: str | None = None
    platform: str
    author: str | None = None
    title: str | None = None
    posted_at: str | None = None


class Manifest(_Model):
    schema_: Literal["skipwatch/manifest/1"] = _tag("skipwatch/manifest/1")
    skipwatch_version: str
    source: ManifestSource
    extracted_at: str
    fetched_with_cookies: bool = False
    counts: Counts
    confidence: Literal["high", "medium", "low"]
    critic_score: float | None = None
    checks_passed: bool
    safety_flags: list[SafetyFlag] = []
    files: dict[str, str] = {}


# ---- other work-folder files (5.3) ----
StageName = Literal[
    "detect",
    "ingest",
    "transcribe",
    "frames",
    "plan",
    "read",
    "distill",
    "critique",
    "check",
    "review",
    "install",
    "export",
]


class StageState(_Model):
    status: Literal["pending", "running", "done", "failed"] = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None


class StagesFile(_Model):
    schema_: Literal["skipwatch/stages/1"] = _tag("skipwatch/stages/1")
    stages: dict[StageName, StageState]


class SourceFile(_Model):
    schema_: Literal["skipwatch/source/1"] = _tag("skipwatch/source/1")
    kind: SourceKind
    platform: str
    url: str | None = None
    canonical_url: str | None = None
    path: str | None = None


class CallsFile(_Model):
    schema_: Literal["skipwatch/calls/1"] = _tag("skipwatch/calls/1")
    calls: list[ProviderCall] = []


class CritiqueFix(_Model):
    step: int
    timestamp: str | None = None
    fix: str


class Critique(_Model):
    schema_: Literal["skipwatch/critique/1"] = _tag("skipwatch/critique/1")
    scores: dict[
        Literal[
            "completeness", "verifiability", "actionability", "trigger_quality", "safety_hygiene"
        ],
        float,
    ]
    score: float = Field(ge=1, le=10)
    fixes: list[CritiqueFix] = Field(default=[], max_length=8)


# ---- command --json outputs ----
Tier = Literal["none", "0", "1", "1c", "2", "3"]


class DoctorComponent(_Model):
    name: str
    found: bool
    version: str | None = None
    detail: str = ""


class DoctorMissing(_Model):
    name: str
    unlocks: str
    install_command: str


class DoctorReport(_Model):
    schema_: Literal["skipwatch/doctor/1"] = _tag("skipwatch/doctor/1")
    tier: Tier
    next_tier: Tier | None = None
    components: list[DoctorComponent]
    missing: list[DoctorMissing]
    warnings: list[str] = []


class CacheResult(_Model):
    schema_: Literal["skipwatch/cache/1"] = _tag("skipwatch/cache/1")
    cleared: bool
    removed: list[str] = []
    cache_entries: int = 0
    work_folders: int = 0


class InstallResult(_Model):
    schema_: Literal["skipwatch/install/1"] = _tag("skipwatch/install/1")
    name: str
    path: str
    scope: Literal["user", "project", "agents", "dir"]
    backup: str | None = None


class RedactionReplacement(_Model):
    kind: str
    placeholder: str
    count: int = 1


SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "ingest": IngestBundle,
    "transcript": Transcript,
    "frames": FramesFile,
    "batches": BatchesFile,
    "notes": NotesFile,
    "check": CheckReport,
    "manifest": Manifest,
    "stages": StagesFile,
    "source": SourceFile,
    "calls": CallsFile,
    "critique": Critique,
    "doctor": DoctorReport,
    "cache": CacheResult,
    "install": InstallResult,
    "config": Config,
}
