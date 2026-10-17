"""Pack pipeline, spec S4 (M5-G1): round trip, tamper and list through the real CLI.

Reuses the M1 fixture pipeline (tests/pipeline/test_fixture_pipeline.py): the reference run
of tests/fixtures/tutorial-60s.mp4 is checked and installed with --to, then packed, unpacked,
checked in pack mode, installed again and packed again. Needs ffmpeg and ffprobe on PATH,
like the pipeline it builds on.
"""

import json
import subprocess
from pathlib import Path

import pytest

from tests.pipeline.test_fixture_pipeline import (  # noqa: F401  (pytest fixtures)
    NAME,
    Engine,
    checked,
    engine,
    root,
    staged,
    staging,
    work,
)

pytestmark = pytest.mark.pipeline

PACKS = Path(__file__).resolve().parents[1] / "fixtures" / "packs"


@pytest.fixture(scope="module")
def home(root: Path) -> Path:  # noqa: F811
    return root / "swhome"  # the SKIPWATCH_HOME of the shared engine fixture


@pytest.fixture(scope="module")
def installed(
    checked: subprocess.CompletedProcess,  # noqa: F811
    staging: Path,  # noqa: F811
    root: Path,  # noqa: F811
    engine: Engine,  # noqa: F811
) -> Path:
    assert checked.returncode == 0, checked.stderr
    engine.ok("install", str(staging), "--to", str(root / "installed"))
    return root / "installed" / NAME


def test_pack_round_trip_is_byte_identical(tmp_path, installed, engine):  # noqa: F811
    p1 = tmp_path / "p1.skillpack.zip"
    p2 = tmp_path / "p2.skillpack.zip"
    engine.ok("pack", str(installed), "-o", str(p1))
    unpacked = json.loads(engine.ok("unpack", str(p1), "--json").stdout)
    checked_pack = engine.run("check", unpacked["staging"], "--work", unpacked["work"])
    assert checked_pack.returncode in (0, 5), checked_pack.stderr
    engine.ok("install", unpacked["staging"], "--to", str(tmp_path / "again"))
    engine.ok("pack", str(tmp_path / "again" / NAME), "-o", str(p2))
    assert p1.read_bytes() == p2.read_bytes()


def test_tamper_test_exits_9_and_installs_nothing(home, engine):  # noqa: F811
    before = set((home / "packs").glob("*"))  # the round trip may have unpacked already
    r = engine.run("unpack", str(PACKS / f"{NAME}-tampered.skillpack.zip"), "--json")
    assert r.returncode == 9 and "SKILL.md: hash mismatch" in r.stderr
    assert set((home / "packs").glob("*")) == before


def test_list_shows_installed_skills(installed, engine):  # noqa: F811
    out = json.loads(engine.ok("list", "--json").stdout)
    assert NAME in {s["name"] for s in out["skills"]}
