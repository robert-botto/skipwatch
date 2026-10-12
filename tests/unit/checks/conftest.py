import os
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image

from skipwatch.checks.runner import CheckContext, build_context
from skipwatch.workdir import WorkDir

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "skills"
NAME = "run-skipdemo-tutorial"
KEY = "sk-proj-FIXTURE0NLY0000000000000000000000000000"
EM_DASH = "\u2014"


@pytest.fixture(autouse=True)
def _isolated_home(sw_home):
    """Checks read config.toml; never let a developer's real ~/.skipwatch leak into tests."""
    return sw_home


def sw_home_work() -> Path:
    from skipwatch.config import skipwatch_home

    return skipwatch_home() / "work"


def write_jpeg(path: Path, width: int = 960, height: int = 540) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (width, height), (30, 30, 30)).save(path, "JPEG")


def make_case(tmp_path: Path, edit: Callable[[str], str] | None = None) -> tuple[Path, Path]:
    """Copy the good skill and the work folder; staging is work/staging/<name>/. The work folder
    sits directly under the test home's work/, where check's --work guard accepts it."""
    work = sw_home_work() / "work"
    shutil.copytree(FIX / "work", work)
    WorkDir(work).ensure()
    staging = work / "staging" / NAME
    shutil.copytree(FIX / "good" / NAME, staging)
    write_jpeg(staging / "assets" / "frames" / "f000250.jpg")
    if edit is not None:
        skill_md = staging / "SKILL.md"
        skill_md.write_text(edit(skill_md.read_text(encoding="utf-8")), encoding="utf-8")
    return staging, work


def context_for(staging: Path, work: Path) -> CheckContext:
    return build_context(staging, work)


def write_manifest(staging: Path, work: Path) -> None:
    """What `check` does before structure runs (plan issue 1), for testing structure alone."""
    from skipwatch.manifest import build
    from skipwatch.models import CheckReport, Counts
    from skipwatch.workdir import write_model

    report = CheckReport(skill=staging.name, passed=True, results=[], counts=Counts())
    write_model(staging / "skipwatch.json", build(staging, work, report))


def symlink_or_skip(link: Path, target: Path, is_dir: bool = False) -> None:
    """Symlinks can need privileges on Windows; skip rather than fail where they are refused."""
    try:
        link.symlink_to(target, target_is_directory=is_dir)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks unavailable here: {exc}")


def hardlink_or_skip(link: Path, target: Path) -> None:
    try:
        os.link(target, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"hardlinks unavailable here: {exc}")
