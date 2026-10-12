import json
from pathlib import Path
from typing import Literal

import pytest
from typer.testing import CliRunner

from skipwatch import installs, listing
from skipwatch.cli import app
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import (
    Counts,
    InstallResult,
    ListResult,
    Manifest,
    ManifestSource,
)
from skipwatch.workdir import write_model


@pytest.fixture
def roots(tmp_path, monkeypatch, sw_home):
    home = tmp_path / "home"
    cwd = tmp_path / "project"
    home.mkdir()
    cwd.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.chdir(cwd)
    return home, cwd


def manifest(name: str, **source) -> Manifest:
    return Manifest(
        name=name,
        description=f"{name} does a thing.",
        skipwatch_version="0.1.0",
        source=ManifestSource(
            platform="youtube",
            url=f"https://youtu.be/{name}",
            author="@creator",
            title=f"How to {name}",
            **source,
        ),
        extracted_at="2026-10-09T12:00:00Z",
        counts=Counts(steps=3, spoken=3),
        confidence="medium",
        critic_score=7.5,
        checks_passed=True,
    )


def make_skill(parent: Path, name: str, folder: str | None = None) -> Path:
    skill = parent / (folder or name)
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
    write_model(skill / "skipwatch.json", manifest(name))
    return skill


def logged(
    path: Path,
    name: str,
    scope: Literal["user", "project", "agents", "dir"] = "dir",
    origin: Literal["run", "pack"] = "run",
) -> None:
    installs.record(InstallResult(name=name, path=str(path), scope=scope), origin)


def test_list_finds_scopes_and_to_installs(roots, tmp_path):
    home, cwd = roots
    user = make_skill(home / ".claude/skills", "alpha")
    project = make_skill(cwd / ".claude/skills", "beta")
    agents = make_skill(cwd / ".agents/skills", "gamma")
    elsewhere = make_skill(tmp_path / "custom", "delta")
    (home / ".claude/skills/plain-skill").mkdir()  # not a SkipWatch skill: no skipwatch.json
    logged(elsewhere, "delta", origin="pack")
    logged(user, "alpha", scope="user")  # recorded and scanned: listed once
    logged(tmp_path / "gone" / "epsilon", "epsilon")  # folder removed since: skipped

    result = listing.scan(cwd, home)
    got = [(s.name, s.scope, Path(s.path), s.origin) for s in result.skills]
    assert got == [
        ("alpha", "user", user.resolve(), "run"),
        ("beta", "project", project.resolve(), "unknown"),
        ("delta", "dir", elsewhere.resolve(), "pack"),
        ("gamma", "agents", agents.resolve(), "unknown"),
    ]
    alpha = result.skills[0]
    assert alpha.title == "How to alpha" and alpha.author == "@creator"
    assert alpha.url == "https://youtu.be/alpha" and alpha.platform == "youtube"
    assert alpha.confidence == "medium" and alpha.critic_score == 7.5
    assert alpha.extracted_at == "2026-10-09T12:00:00Z" and alpha.problem is None


def test_list_prefers_canonical_url(roots):
    home, cwd = roots
    skill = make_skill(home / ".claude/skills", "alpha")
    write_model(
        skill / "skipwatch.json", manifest("alpha", canonical_url="https://www.youtube.com/x")
    )
    assert listing.scan(cwd, home).skills[0].url == "https://www.youtube.com/x"


def test_list_unreadable_manifest_has_problem(roots, tmp_path):
    home, cwd = roots
    broken = make_skill(home / ".claude/skills", "broken")
    (broken / "skipwatch.json").write_text("{not json", encoding="utf-8")
    recorded = tmp_path / "custom" / "no-manifest"
    recorded.mkdir(parents=True)
    logged(recorded, "no-manifest")
    skills = listing.scan(cwd, home).skills
    assert [(s.name, s.scope, s.problem) for s in skills] == [
        ("broken", "user", "unreadable skipwatch.json"),
        ("no-manifest", "dir", "unreadable skipwatch.json"),
    ]
    assert skills[0].title is None and skills[0].confidence is None


def test_r_man_1_list_reads_only_manifests(roots, tmp_path, monkeypatch):
    home, cwd = roots
    make_skill(home / ".claude/skills", "alpha")
    make_skill(cwd / ".agents/skills", "gamma")
    logged(make_skill(tmp_path / "custom", "delta"), "delta")
    read: list[str] = []
    real_text, real_bytes = Path.read_text, Path.read_bytes

    def spy_text(self, *args, **kwargs):
        read.append(self.name)
        return real_text(self, *args, **kwargs)

    def spy_bytes(self):
        read.append(self.name)
        return real_bytes(self)

    monkeypatch.setattr(Path, "read_text", spy_text)
    monkeypatch.setattr(Path, "read_bytes", spy_bytes)
    assert len(listing.scan(cwd, home).skills) == 3
    assert set(read) == {"skipwatch.json", installs.INSTALLS}
    assert read.count("skipwatch.json") == 3


def test_list_same_folder_for_two_scopes_is_listed_once(roots, monkeypatch):
    home, _ = roots
    make_skill(home / ".claude/skills", "alpha")
    skills = listing.scan(home, home).skills  # cwd is home: project scope is the user folder
    assert [(s.name, s.scope) for s in skills] == [("alpha", "user")]


def run_list(*args: str):
    return CliRunner().invoke(app, ["list", *args])


def test_list_json_validates(roots, tmp_path):
    home, _ = roots
    make_skill(home / ".claude/skills", "alpha")
    r = run_list("--json")
    assert r.exit_code == 0, r.stderr
    result = ListResult.model_validate_json(r.stdout)
    assert [s.name for s in result.skills] == ["alpha"]
    assert json.loads(r.stdout)["schema"] == "skipwatch/list/1"


def test_list_human_lines(roots):
    home, _ = roots
    skill = make_skill(home / ".claude/skills", "alpha")
    r = run_list()
    assert r.exit_code == 0 and r.stdout == ""
    assert r.stderr.strip() == (
        f'alpha  medium  "How to alpha" by @creator  2026-10-09  user  {skill.resolve()}'
    )


def test_list_none_installed(roots):
    r = run_list()
    assert r.exit_code == 0
    assert r.stderr.strip() == "No SkipWatch skills installed."


def test_list_problem_line(roots):
    home, _ = roots
    broken = make_skill(home / ".claude/skills", "broken")
    (broken / "skipwatch.json").write_text("[]", encoding="utf-8")
    r = run_list()
    assert r.stderr.strip() == f"broken  ?  unreadable skipwatch.json  user  {broken.resolve()}"


def test_locate_name_path_missing_and_ambiguous(roots, tmp_path):
    home, cwd = roots
    user = make_skill(home / ".claude/skills", "alpha")
    # a path to a folder with skipwatch.json is returned as is, even when not installed
    loose = make_skill(tmp_path / "loose", "loose")
    assert listing.locate(str(loose), cwd, home) == loose
    # a name resolves through the scan
    assert listing.locate("alpha", cwd, home) == user.resolve()
    # a folder without skipwatch.json is not a path match, and no skill has that name
    (tmp_path / "plain").mkdir()
    with pytest.raises(SkipwatchError) as exc:
        listing.locate(str(tmp_path / "plain"), cwd, home)
    assert exc.value.code == ExitCode.UNSUPPORTED_SOURCE
    with pytest.raises(SkipwatchError) as exc:
        listing.locate("nope", cwd, home)
    assert exc.value.code == ExitCode.UNSUPPORTED_SOURCE
    assert exc.value.message == (
        "no installed SkipWatch skill named nope; /skipwatch list shows them"
    )
    other = make_skill(cwd / ".claude/skills", "alpha")
    with pytest.raises(SkipwatchError) as exc:
        listing.locate("alpha", cwd, home)
    assert exc.value.code == ExitCode.USAGE
    assert str(user.resolve()) in exc.value.message
    assert str(other.resolve()) in exc.value.message
    assert "pass the path instead" in exc.value.message


def test_locate_relative_path_is_from_cwd(roots):
    home, cwd = roots
    make_skill(cwd / "skills", "alpha")
    assert listing.locate(str(Path("skills") / "alpha"), cwd, home) == cwd / "skills" / "alpha"
