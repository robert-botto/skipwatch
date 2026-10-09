"""Work folder layout, atomic model files and stages.json bookkeeping (R-WORK-1)."""

import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import BaseModel

from skipwatch.config import skipwatch_home
from skipwatch.models import StageName, StagesFile, StageState

T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)

StageStatus = Literal["pending", "running", "done", "failed"]

STAGE_ORDER: tuple[StageName, ...] = (
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
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_model(path: Path, model: BaseModel) -> None:
    """Write JSON by alias atomically: temp file in the same folder, then os.replace."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(model.model_dump_json(by_alias=True, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_model(path: Path, cls: type[M]) -> M:
    return cls.model_validate_json(path.read_text(encoding="utf-8"))


def new_work_path(slug: str, now: datetime) -> Path:
    return skipwatch_home() / "work" / f"{slug}-{now:%Y%m%d-%H%M%S}"


class WorkDir:
    def __init__(self, path: Path):
        self.path = path

    def file(self, name: str) -> Path:
        return self.path / name

    def ensure(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        if not self.file("stages.json").exists():
            stages = StagesFile(stages={name: StageState() for name in STAGE_ORDER})
            write_model(self.file("stages.json"), stages)

    def stages(self) -> StagesFile:
        return read_model(self.file("stages.json"), StagesFile)

    def mark(self, stage: StageName, status: StageStatus, error: str | None = None) -> None:
        stages = self.stages()
        state = stages.stages.get(stage, StageState())
        if status == "running":
            state = StageState(status="running", started_at=_now())
        else:
            state = state.model_copy(update={"status": status, "error": error})
            if status in ("done", "failed"):
                state.finished_at = _now()
        stages.stages[stage] = state
        write_model(self.file("stages.json"), stages)

    def first_incomplete(self) -> StageName | None:
        stages = self.stages().stages
        for name in STAGE_ORDER:
            if name not in stages or stages[name].status != "done":
                return name
        return None


def run_stage(work: WorkDir, stage: StageName, fn: Callable[[], T]) -> T:
    """Mark running, call fn (which writes its output file), then mark done or failed."""
    work.mark(stage, "running")
    try:
        result = fn()
    except Exception as exc:
        message = getattr(exc, "message", None) or str(exc)
        work.mark(stage, "failed", error=message)
        raise
    work.mark(stage, "done")
    return result
