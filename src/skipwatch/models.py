"""Pydantic models for every file SkipWatch writes (R-ARCH-2). schemas/ is generated from here."""

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def _tag(value: str) -> Any:
    return Field(default=value, alias="schema")


def _schema_tag_required(schema: dict[str, Any]) -> None:
    required = schema.setdefault("required", [])
    if "schema" not in required:
        required.insert(0, "schema")


class _Tagged(_Model):
    """A model written to disk with a `schema` tag.

    Reading (model_validate, model_validate_json) requires the tag, and the generated JSON Schema
    lists it as required. Constructing in Python fills it in: __init__ injects the field default
    before validation. __init__ is marked as a base init (the pattern pydantic's own RootModel
    uses) so model_validate validates the raw data directly and never reaches the injection.
    The field keeps its default so type checkers accept construction without it.
    """

    model_config = ConfigDict(json_schema_extra=_schema_tag_required)

    def __init__(self, **data: Any) -> None:
        if "schema" not in data and "schema_" not in data:
            data["schema"] = type(self).model_fields["schema_"].default
        super().__init__(**data)

    __init__.__pydantic_base_init__ = True  # pyright: ignore[reportFunctionMemberAccess]

    @model_validator(mode="before")
    @classmethod
    def _require_schema_tag(cls, data: Any) -> Any:
        if isinstance(data, dict) and "schema" not in data and "schema_" not in data:
            raise ValueError("missing schema tag: expected 'schema' key")
        return data


# ---- config.toml (7.7) ----
class _ConfigModel(_Model):
    """Config is hand-written TOML: no coercion, so per_minute = "5" is an error."""

    model_config = ConfigDict(strict=True)


class InstallConfig(_ConfigModel):
    scope: Literal["user", "project", "agents"] = "user"


class FramesConfig(_ConfigModel):
    per_minute: int = Field(default=3, ge=1)
    max: int = Field(default=60, ge=1)


class TranscribeConfig(_ConfigModel):
    backend: Literal["auto", "captions", "mlx", "faster", "openai", "groq", "deepgram"] = "auto"
    model: str = ""


class TregConfig(_ConfigModel):
    enabled: Literal["auto", True, False] = "auto"
    max_cost_usd: float = Field(default=0.05, ge=0)  # per run (M2-M4 issue 9)


class ProvidersConfig(_ConfigModel):
    treg: TregConfig = TregConfig()


class StyleConfig(_ConfigModel):
    forbid: list[str] = ["em-dash"]


class Mem0Config(_ConfigModel):
    enabled: bool = False
    tag: str = "skipwatch"
    user_id: str = ""  # empty sends agent_id "skipwatch" (M5-M6 issue 8); the key is env only


class NotesConfig(_ConfigModel):
    enabled: bool = False
    folder: str = ""


class ExportsConfig(_ConfigModel):
    mem0: Mem0Config = Mem0Config()
    notes: NotesConfig = NotesConfig()


class Config(_ConfigModel):
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
    captions_lang: str | None = None
    captions_kind: Literal["manual", "auto"] | None = None


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
    endpoint: str | None = None
    call_id: str | None = None
    review: Literal["useful", "partly", "not_useful", "not_sure"] | None = None
    error: str | None = None


class Route(_Model):
    context: str
    media: str | None = None
    fallbacks: list[str] = []


class IngestBundle(_Tagged):
    schema_: Literal["skipwatch/ingest/1"] = _tag("skipwatch/ingest/1")
    source: SourceInfo
    context: IngestContext = IngestContext()
    media: MediaInfo | None = None
    transcript_hint: TranscriptHint = TranscriptHint()
    provider_calls: list[ProviderCall] = []
    route: Route
    fetched_with_cookies: bool = False
    from_cache: bool = False
    pack: "PackOrigin | None" = None  # set only by unpack; the one switch for pack mode


# ---- transcript.json (7.2) ----
TranscriptOrigin = Literal[
    "captions", "mlx-whisper", "faster-whisper", "openai", "groq", "deepgram", "pack"
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


class Transcript(_Tagged):
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


class FramesFile(_Tagged):
    schema_: Literal["skipwatch/frames/1"] = _tag("skipwatch/frames/1")
    sampling: Sampling
    frames: list[Frame]


# ---- batches.json and notes/batch-NN.json (7.4) ----
class Batch(_Model):
    id: int = Field(ge=1)
    frame_ids: list[str]
    notes_path: str


class BatchesFile(_Tagged):
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


class NotesFile(_Tagged):
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


class CheckReport(_Tagged):
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


class Manifest(_Tagged):
    schema_: Literal["skipwatch/manifest/1"] = _tag("skipwatch/manifest/1")
    name: str
    description: str
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


class PackOrigin(_Model):
    """Where an unpacked skill came from (M5-M6 issue 1): carried in a pack work folder's
    ingest.json so check and manifest building know they are looking at a shared pack."""

    file: str  # pack file name or URL as given
    sha256: str  # "sha256:<hex>" of the pack bytes
    manifest: Manifest  # the pack's skipwatch.json exactly as received


IngestBundle.model_rebuild()


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


class StagesFile(_Tagged):
    schema_: Literal["skipwatch/stages/1"] = _tag("skipwatch/stages/1")
    stages: dict[StageName, StageState]


class SourceFile(_Tagged):
    schema_: Literal["skipwatch/source/1"] = _tag("skipwatch/source/1")
    kind: SourceKind
    platform: str
    url: str | None = None
    canonical_url: str | None = None
    path: str | None = None


class CallsFile(_Tagged):
    schema_: Literal["skipwatch/calls/1"] = _tag("skipwatch/calls/1")
    calls: list[ProviderCall] = []


class CritiqueFix(_Model):
    step: int
    timestamp: str | None = None
    fix: str


class Critique(_Tagged):
    schema_: Literal["skipwatch/critique/1"] = _tag("skipwatch/critique/1")
    scores: dict[
        Literal[
            "completeness", "verifiability", "actionability", "trigger_quality", "safety_hygiene"
        ],
        float,
    ]
    score: float = Field(ge=1, le=10)
    fixes: list[CritiqueFix] = Field(default=[], max_length=8)


class RunFile(_Tagged):
    """run.json: the original input and flags, written by the orchestrator before ingest."""

    schema_: Literal["skipwatch/run/1"] = _tag("skipwatch/run/1")
    input: str
    flags: list[str] = []
    name: str | None = None
    started_at: str


class CacheEntry(_Tagged):
    schema_: Literal["skipwatch/cache-entry/1"] = _tag("skipwatch/cache-entry/1")
    key: str
    source: str
    created_at: str
    files: list[str] = []


class InstallRecord(_Model):
    name: str
    path: str
    scope: Literal["user", "project", "agents", "dir"]
    origin: Literal["run", "pack"] = "run"
    installed_at: str


class InstallsFile(_Tagged):
    """$SKIPWATCH_HOME/installs.json: every install, so list finds --to installs (issue 10)."""

    schema_: Literal["skipwatch/installs/1"] = _tag("skipwatch/installs/1")
    installs: list[InstallRecord] = []


class ExportLogEntry(_Model):
    provider: str
    name: str
    manifest_sha256: str  # sha256 of the skipwatch.json bytes that were exported
    ref: str | None = None
    exported_at: str


class ExportLog(_Tagged):
    """$SKIPWATCH_HOME/exports.json: re-exporting an unchanged skill is a no-op (issue 9)."""

    schema_: Literal["skipwatch/export-log/1"] = _tag("skipwatch/export-log/1")
    entries: list[ExportLogEntry] = []


class TesterReport(_Tagged):
    """test-report.json from the skill-tester agent (8.9). Named TesterReport, not TestReport,
    so pytest never tries to collect it (M5-M6 issue 25)."""

    __test__: ClassVar[bool] = False  # the name still starts with "Test" for pytest's matcher

    schema_: Literal["skipwatch/test-report/1"] = _tag("skipwatch/test-report/1")
    outcome: Literal["completed", "blocked", "ambiguous"]
    step: int | None = Field(default=None, ge=1)
    detail: str = Field(default="", max_length=500)
    task: str

    @model_validator(mode="after")
    def _stopped_runs_name_the_step(self) -> "TesterReport":
        if self.outcome != "completed" and (self.step is None or not self.detail.strip()):
            raise ValueError(f"{self.outcome} needs a step and a detail")
        return self


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


class DoctorReport(_Tagged):
    schema_: Literal["skipwatch/doctor/1"] = _tag("skipwatch/doctor/1")
    tier: Tier
    next_tier: Tier | None = None
    components: list[DoctorComponent]
    missing: list[DoctorMissing]
    warnings: list[str] = []


class CacheResult(_Tagged):
    schema_: Literal["skipwatch/cache/1"] = _tag("skipwatch/cache/1")
    cleared: bool
    removed: list[str] = []
    cache_entries: int = 0
    work_folders: int = 0


class InstallResult(_Tagged):
    schema_: Literal["skipwatch/install/1"] = _tag("skipwatch/install/1")
    name: str
    path: str
    scope: Literal["user", "project", "agents", "dir"]
    backup: str | None = None


class ProbeResult(_Tagged):
    schema_: Literal["skipwatch/probe/1"] = _tag("skipwatch/probe/1")
    value: str
    kind: Literal["video", "audio", "text", "file", "unknown"]
    platform: str
    title: str | None = None
    author: str | None = None
    duration_s: float | None = None
    captions_available: bool = False
    long_video: bool = False
    estimated_run_s: int | None = None


class ResumeResult(_Tagged):
    schema_: Literal["skipwatch/resume/1"] = _tag("skipwatch/resume/1")
    work: str
    next_stage: StageName | None
    completed: list[StageName] = []
    run: RunFile | None = None
    media_present: bool = False


class PackResult(_Tagged):
    schema_: Literal["skipwatch/pack/1"] = _tag("skipwatch/pack/1")
    name: str
    path: str
    sha256: str  # "sha256:<hex>" of the pack file, for the recipient to compare (issue 3)
    files: int
    bytes: int
    ignored: list[str] = []  # Finder and Windows junk left out of the pack


class UnpackResult(_Tagged):
    schema_: Literal["skipwatch/unpack/1"] = _tag("skipwatch/unpack/1")
    name: str
    work: str  # the pack work folder under $SKIPWATCH_HOME/packs/ (issue 1)
    staging: str
    pack_sha256: str
    files: int
    fetched_from: str | None = None
    claimed_confidence: Literal["high", "medium", "low"]
    claimed_critic_score: float | None = None
    transcript: bool  # True when transcript.json was rebuilt from references/transcript.md


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
    "probe": ProbeResult,
    "run": RunFile,
    "resume": ResumeResult,
    "cache-entry": CacheEntry,
    "installs": InstallsFile,
    "export-log": ExportLog,
    "test-report": TesterReport,
    "pack": PackResult,
    "unpack": UnpackResult,
}
