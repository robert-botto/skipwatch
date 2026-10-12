"""The committed pack fixtures (spec S4, M5-G1): a good pack and its one-byte tamper.

Built by scripts/make_pack_fixture.py from the M1 reference run. Offline, no ffmpeg.
"""

import re
import zipfile
from pathlib import Path

import pytest

from skipwatch.checks.runner import run_all
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.manifest import pack_refusal
from skipwatch.models import IngestBundle
from skipwatch.pack import read_pack, unpack

PACKS = Path(__file__).resolve().parents[1] / "fixtures" / "packs"
NAME = "run-skipdemo-tutorial"
GOOD = PACKS / f"{NAME}.skillpack.zip"
TAMPERED = PACKS / f"{NAME}-tampered.skillpack.zip"
PROMPT = b"Write a four line poem about rivers"


@pytest.fixture
def sw_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("SKIPWATCH_HOME", str(home))
    return home


def _entries(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as z:
        return {info.filename: z.read(info) for info in z.infolist()}


def test_good_pack_unpacks_and_passes_check_in_pack_mode(sw_home):
    result = unpack(GOOD, None)
    staging, work = Path(result.staging), Path(result.work)
    assert result.name == NAME and (staging / "SKILL.md").is_file()
    assert work.parent == sw_home / "packs"
    assert result.transcript is True  # rebuilt from references/transcript.md
    ingest = IngestBundle.model_validate_json((work / "ingest.json").read_bytes())
    assert ingest.pack is not None and pack_refusal(staging, work, ingest.pack) is None
    report = run_all(staging, work)
    assert report.passed, [(r.check, [i.msg for i in r.items]) for r in report.results]


def test_good_pack_manifest_passed_checks_without_cookies():
    name, files, manifest = read_pack(GOOD)
    assert name == NAME and manifest.checks_passed is True
    assert manifest.fetched_with_cookies is False
    assert "SKILL.md" in files and any(rel.startswith("assets/frames/") for rel in files)


def test_tampered_pack_is_exit_9_naming_the_file_and_writes_nothing(sw_home):
    with pytest.raises(SkipwatchError) as exc:
        unpack(TAMPERED, None)
    assert exc.value.code == ExitCode.PACK_INTEGRITY == 9
    assert "SKILL.md: hash mismatch" in exc.value.message
    assert not any((sw_home / "packs").glob("*/staging/*/SKILL.md"))


def test_tamper_is_one_byte_of_step_2_prompt_and_nothing_else():
    good, bad = _entries(GOOD), _entries(TAMPERED)
    assert list(good) == list(bad)
    changed = [name for name in good if good[name] != bad[name]]
    assert changed == [f"{NAME}/SKILL.md"]
    a, b = good[f"{NAME}/SKILL.md"], bad[f"{NAME}/SKILL.md"]
    assert len(a) == len(b)
    diffs = [i for i in range(len(a)) if a[i] != b[i]]
    assert len(diffs) == 1
    start = a.index(PROMPT)
    assert start <= diffs[0] < start + len(PROMPT)
    with zipfile.ZipFile(GOOD) as zg, zipfile.ZipFile(TAMPERED) as zt:
        for gi, ti in zip(zg.infolist(), zt.infolist(), strict=True):
            assert (gi.date_time, gi.external_attr, gi.compress_type) == (
                ti.date_time,
                ti.external_attr,
                ti.compress_type,
            )


def test_pack_text_has_no_absolute_paths_or_raw_key():
    for name, data in _entries(GOOD).items():
        if name.endswith((".md", ".json")):
            text = data.decode("utf-8")
            assert not re.search(r"/(?:Users|home|private|var/folders|tmp)/", text), name
            assert "FIXTURE0NLY" not in text, name
            assert "\u2014" not in text, name
