"""Draft and staging housekeeping for the check retry and the review screen (skill audit 7).

drop removes one file from <W>/draft and <W>/staging/<name>; every path is checked before
anything is deleted, with the same guards as redact (home_work_or_pack_folder, path_under).
rename-staging moves the one staging folder to a new skill name and records it in run.json;
the draft is name-agnostic (<W>/draft/<path>), so it stays where it is.
"""

import json
import os
from pathlib import Path, PurePosixPath
from typing import Annotated

import typer

from skipwatch.checks.frontmatter import is_skill_name
from skipwatch.commands.workfiles import home_work_or_pack_folder, path_under
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.output import progress
from skipwatch.runner import run_command
from skipwatch.workdir import write_bytes_atomic

# check writes skipwatch.json, and SKILL.md is the skill itself: neither is dropped
KEPT_FILES = ("SKILL.md", "skipwatch.json")


def _usage(message: str) -> SkipwatchError:
    return SkipwatchError(ExitCode.USAGE, message)


def _run_name(work: Path) -> str | None:
    """run.json's `name`, if the file and the field are there; a name that breaks the
    skill-name rule is refused, since it becomes a folder under staging/."""
    run = work / "run.json"
    if run.is_symlink():
        raise _usage(f"{run} is a symlink")
    try:
        data = json.loads(run.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    name = data.get("name") if isinstance(data, dict) else None
    if name is None:
        return None
    if not isinstance(name, str) or not is_skill_name(name):
        raise _usage(f"run.json name {name!r} is not a skill name")
    return name


def staging_name(work: Path) -> str | None:
    """The run's staging folder: run.json's name when set, else the one folder under
    <W>/staging. None when there is no staging folder yet; exit 64 when there are several."""
    name = _run_name(work)
    if name is not None:
        return name
    staging = work / "staging"
    if staging.is_symlink():
        raise _usage(f"{staging} is a symlink")
    if not staging.is_dir():
        return None
    folders = sorted(p.name for p in staging.iterdir() if p.is_dir() or p.is_symlink())
    if len(folders) > 1:
        raise _usage(f"{staging} holds {len(folders)} folders and run.json names none")
    return folders[0] if folders else None


def _relative(rel: str) -> PurePosixPath:
    """--path as a plain relative POSIX file path inside a skill folder."""
    path = PurePosixPath(rel)
    if (
        not rel
        or "\\" in rel
        or path.is_absolute()
        or ".." in path.parts
        or not path.parts
        or str(path) in KEPT_FILES
    ):
        raise _usage(f"--path {rel!r} must be a relative file path with no .., not {KEPT_FILES}")
    return path


def _drop(work: Path, rel: str) -> int:
    work = home_work_or_pack_folder(work)
    path = _relative(rel)
    copies = [path_under(work, "draft", work / "draft" / path, "--path")]
    name = staging_name(work)
    if name is not None:
        copies.append(path_under(work, "staging", work / "staging" / name / path, "--path"))
    present = [copy for copy in copies if os.path.lexists(copy)]
    for copy in present:
        if copy.is_symlink() or not copy.is_file():
            raise _usage(f"--path {copy} is not a file")
    for copy in present:
        copy.unlink()
        progress(f"Dropped: {copy}")
    if not present:
        progress(f"Drop: no copy of {path} in {work}")
    return 0


def _run_json(work: Path) -> dict[str, object]:
    run = work / "run.json"
    if run.is_symlink():
        raise _usage(f"{run} is a symlink")
    try:
        data = json.loads(run.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _usage(f"{run} does not read: {exc}") from exc
    if not isinstance(data, dict):
        raise _usage(f"{run} is not a JSON object")
    return data


def _rename_staging(work: Path, to: str) -> int:
    work = home_work_or_pack_folder(work)
    if not is_skill_name(to):
        raise _usage(f"--to {to!r} must be lowercase letters, digits and single hyphens, 1-64")
    data = _run_json(work)
    staging = work / "staging"
    if staging.is_symlink():
        raise _usage(f"{staging} is a symlink")
    name = staging_name(work)
    old = staging / (name or "")
    if name is None or old.is_symlink() or not old.is_dir():
        raise _usage(f"no staging folder to rename in {staging}")
    target = staging / to
    if name != to:
        if os.path.lexists(target):
            raise SkipwatchError(ExitCode.TARGET_EXISTS, f"{target} exists")
        os.rename(old, target)
    data["name"] = to
    try:
        write_bytes_atomic(work / "run.json", (json.dumps(data, indent=2) + "\n").encode("utf-8"))
    except BaseException:
        if name != to:
            os.rename(target, old)
        raise
    progress(f"Renamed: {old} -> {target}")
    return 0


def register(app: typer.Typer) -> None:
    @app.command("drop")
    def _drop_cmd(
        work: Annotated[Path, typer.Option("--work", help="The run's work folder.")],
        path: Annotated[
            str, typer.Option("--path", help="The file's path inside the skill, e.g. assets/a.zip.")
        ],
    ):
        """Delete one file from <work>/draft and <work>/staging/<name> (files only)."""
        run_command(lambda: _drop(work, path))

    @app.command("rename-staging")
    def _rename_cmd(
        work: Annotated[Path, typer.Option("--work", help="The run's work folder.")],
        to: Annotated[str, typer.Option("--to", help="The new skill name.")],
    ):
        """Move <work>/staging/<name> to <work>/staging/<to> and set run.json's name."""
        run_command(lambda: _rename_staging(work, to))
