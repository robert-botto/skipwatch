import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_versions.py"


def _copy(tmp_path):
    for rel in [
        "pyproject.toml",
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
        "src/skipwatch/__init__.py",
    ]:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, dst)
    return tmp_path


def _bump_pyproject(root):
    p = root / "pyproject.toml"
    p.write_text(p.read_text().replace('version = "0.1.0"', 'version = "9.9.9"', 1))


def _bump_plugin(root):
    p = root / ".claude-plugin/plugin.json"
    data = json.loads(p.read_text())
    data["version"] = "9.9.9"
    p.write_text(json.dumps(data))


def _bump_marketplace(root):
    p = root / ".claude-plugin/marketplace.json"
    data = json.loads(p.read_text())
    data["plugins"][0]["version"] = "9.9.9"
    p.write_text(json.dumps(data))


def _bump_init(root):
    p = root / "src/skipwatch/__init__.py"
    p.write_text(p.read_text().replace('__version__ = "0.1.0"', '__version__ = "9.9.9"'))


def _run(root):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)], capture_output=True, text=True
    )


@pytest.mark.parametrize(
    ("bump", "source"),
    [
        (_bump_pyproject, "pyproject"),
        (_bump_plugin, "plugin.json"),
        (_bump_marketplace, "marketplace.json"),
        (_bump_init, "skipwatch.__version__"),
    ],
)
def test_r_arch_3_fails_on_drift(tmp_path, bump, source):
    root = _copy(tmp_path)
    bump(root)
    r = _run(root)
    assert r.returncode == 1, r.stdout
    assert any(line.startswith("MISMATCH") and source in line for line in r.stdout.splitlines()), (
        r.stdout
    )


def test_r_arch_3_fails_without_skipwatch_marketplace_entry(tmp_path):
    root = _copy(tmp_path)
    p = root / ".claude-plugin/marketplace.json"
    data = json.loads(p.read_text())
    data["plugins"] = [e for e in data["plugins"] if e["name"] != "skipwatch"]
    p.write_text(json.dumps(data))
    r = _run(root)
    assert r.returncode == 1 and "marketplace.json" in r.stdout, r.stdout


def test_r_arch_3_passes_on_repo():
    r = _run(ROOT)
    assert r.returncode == 0, r.stdout
