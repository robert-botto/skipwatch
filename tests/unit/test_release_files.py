"""Release artifacts: what `uv build` ships, and the plugin manifests (spec 13, issue 13)."""

import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SDIST_LIMIT_BYTES = 200 * 1024
SDIST_FORBIDDEN_TOP = {"tests", "docs", "evals", ".github", "examples", "scripts", "skills"}


@pytest.fixture(scope="module")
def dist(tmp_path_factory):
    if shutil.which("uv") is None:
        pytest.skip("uv not installed")
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(
        ["uv", "build", "--out-dir", str(out), str(ROOT)],
        check=True,
        capture_output=True,
        text=True,
    )
    return out


@pytest.mark.pipeline
def test_wheel_holds_only_the_package(dist):
    (wheel,) = dist.glob("*.whl")
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    assert "skipwatch/__init__.py" in names
    strays = [n for n in names if not n.startswith(("skipwatch/", "skipwatch-")) or "/tests/" in n]
    assert strays == []
    assert all(n.split("/")[0].endswith(".dist-info") for n in names if n.startswith("skipwatch-"))


@pytest.mark.pipeline
def test_sdist_is_the_allowlist_only(dist):
    (sdist,) = dist.glob("*.tar.gz")
    with tarfile.open(sdist) as tf:
        names = tf.getnames()
    tops = {Path(n).parts[1] for n in names if len(Path(n).parts) > 1}
    assert tops & SDIST_FORBIDDEN_TOP == set(), sorted(tops)
    assert {"src", "pyproject.toml", "README.md", "LICENSE", "PKG-INFO"} <= tops, sorted(tops)
    assert sdist.stat().st_size < SDIST_LIMIT_BYTES, sdist.stat().st_size


@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed")
@pytest.mark.parametrize("target", [".", ".claude-plugin/plugin.json"])
def test_claude_plugin_validate_strict(target):
    r = subprocess.run(
        ["claude", "plugin", "validate", "--strict", target],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stdout + r.stderr
