"""The shipped example skills stay exactly as SkipWatch installed them (M6-D)."""

from pathlib import Path

import pytest
import yaml

from skipwatch.models import Manifest
from skipwatch.pack import MANIFEST_NAME, verify_files
from skipwatch.skillmd import _split_frontmatter

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
FRONTMATTER_KEYS = {"name", "description", "license", "compatibility", "metadata"}
EM_DASH = "\u2014"


def example_dirs() -> list[Path]:
    if not EXAMPLES.is_dir():
        return []
    return sorted(p for p in EXAMPLES.iterdir() if p.is_dir())


def manifest(folder: Path) -> Manifest:
    return Manifest.model_validate_json((folder / MANIFEST_NAME).read_bytes())


def test_exactly_three_examples() -> None:
    assert len(example_dirs()) == 3


@pytest.mark.parametrize("folder", example_dirs(), ids=lambda p: p.name)
def test_files_match_manifest_hashes(folder: Path) -> None:
    assert verify_files(folder, manifest(folder)) == []


@pytest.mark.parametrize("folder", example_dirs(), ids=lambda p: p.name)
def test_manifest_is_clean(folder: Path) -> None:
    m = manifest(folder)
    assert m.checks_passed is True
    assert m.safety_flags == []
    assert m.fetched_with_cookies is False
    assert m.name == folder.name


@pytest.mark.parametrize("folder", example_dirs(), ids=lambda p: p.name)
def test_frontmatter_keys_are_allowed(folder: Path) -> None:
    raw, _, _, error = _split_frontmatter((folder / "SKILL.md").read_text(encoding="utf-8"))
    assert error is None
    meta = yaml.safe_load(raw)
    assert set(meta) <= FRONTMATTER_KEYS


@pytest.mark.parametrize("folder", example_dirs(), ids=lambda p: p.name)
def test_no_frames_shipped(folder: Path) -> None:
    assert not (folder / "assets" / "frames").exists()


@pytest.mark.parametrize("folder", example_dirs(), ids=lambda p: p.name)
def test_no_illegible_marker_in_quotes(folder: Path) -> None:
    for path in folder.rglob("*.md"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith(">"):
                assert "[illegible" not in line, f"{path.relative_to(EXAMPLES)}: {line}"


def test_no_em_dash_in_examples() -> None:
    offenders = [
        str(path.relative_to(EXAMPLES))
        for path in EXAMPLES.rglob("*")
        if path.is_file() and EM_DASH in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
