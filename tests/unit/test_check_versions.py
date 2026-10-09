import json
import shutil
import subprocess
import sys
from pathlib import Path

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


def test_r_arch_3_fails_on_plugin_json_drift(tmp_path):
    root = _copy(tmp_path)
    p = root / ".claude-plugin/plugin.json"
    data = json.loads(p.read_text())
    data["version"] = "9.9.9"
    p.write_text(json.dumps(data))
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)], capture_output=True, text=True
    )
    assert r.returncode == 1 and "plugin.json" in r.stdout


def test_r_arch_3_passes_on_repo():
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(ROOT)], capture_output=True, text=True
    )
    assert r.returncode == 0, r.stdout
