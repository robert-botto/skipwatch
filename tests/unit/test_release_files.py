"""Release artifacts: what `uv build` ships, and the plugin manifests (spec 13, issue 13)."""

import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest
import yaml

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


RELEASE_YML = ROOT / ".github" / "workflows" / "release.yml"
CHANGELOG_SECTION = ROOT / "scripts" / "changelog_section.py"
PUBLISH_ACTION = "pypa/gh-action-pypi-publish@"


def _release():
    data = yaml.safe_load(RELEASE_YML.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _uses(job):
    return [step["uses"] for step in job["steps"] if "uses" in step]


def test_release_triggers_on_version_tags_and_dispatch():
    data = _release()
    on = data[True]  # PyYAML reads the bare key `on` as a boolean
    assert on["push"] == {"tags": ["v*.*.*"]}
    assert "workflow_dispatch" in on
    assert data["permissions"] == {"contents": "read"}


@pytest.mark.parametrize(
    ("job", "event", "environment"),
    [("pypi", "push", "pypi"), ("testpypi", "workflow_dispatch", "testpypi")],
)
def test_publish_jobs_use_trusted_publishing(job, event, environment):
    spec = _release()["jobs"][job]
    assert spec["environment"] == environment
    assert spec["permissions"] == {"id-token": "write"}
    assert spec["if"] == f"github.event_name == '{event}'"
    (step,) = [s for s in spec["steps"] if s.get("uses", "").startswith(PUBLISH_ACTION)]
    assert step.get("with", {}).get("attestations") is True
    test_index = step.get("with", {}).get("repository-url")
    assert (test_index == "https://test.pypi.org/legacy/") == (environment == "testpypi")


def test_publish_action_is_pinned_to_a_commit_sha():
    text = RELEASE_YML.read_text(encoding="utf-8")
    pins = re.findall(rf"{re.escape(PUBLISH_ACTION)}(\S+)", text)
    assert len(pins) == 2
    assert all(re.fullmatch(r"[0-9a-f]{40}", pin) for pin in pins), pins
    assert len(set(pins)) == 1


def test_only_github_release_can_write_contents():
    jobs = _release()["jobs"]
    writers = sorted(
        name for name, job in jobs.items() if job.get("permissions", {}).get("contents") == "write"
    )
    assert writers == ["github-release"]
    assert jobs["github-release"]["permissions"] == {"contents": "write"}
    assert jobs["github-release"]["needs"] == "pypi"


def _changelog_section(tmp_path, tag, text):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(text, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(CHANGELOG_SECTION), tag, "--changelog", str(changelog)],
        capture_output=True,
        text=True,
    )


CHANGELOG = """# Changelog

## [Unreleased]

- Not yet.

## [0.1.0] - 2026-10-12

### Added

- First release.

## [0.0.9] - 2026-01-01

- Older.
"""


def test_changelog_section_prints_the_version_body(tmp_path):
    r = _changelog_section(tmp_path, "v0.1.0", CHANGELOG)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "### Added\n\n- First release.\n"


def test_changelog_section_exits_1_when_missing(tmp_path):
    r = _changelog_section(tmp_path, "v0.2.0", CHANGELOG)
    assert r.returncode == 1
    assert r.stdout == ""
    assert "0.2.0" in r.stderr
