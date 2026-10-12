"""Find installed SkipWatch skills (spec 4.2, M5-M6 issue 10).

A SkipWatch skill is a folder holding skipwatch.json. `scan` looks in the three scope folders and
at every path in the install log, and reads nothing but each skill's skipwatch.json (R-MAN-1).
"""

from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from skipwatch import installs
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.manifest import MANIFEST_NAME
from skipwatch.models import InstallRecord, ListedSkill, ListResult, Manifest

ListScope = Literal["user", "project", "agents", "dir"]
UNREADABLE = f"unreadable {MANIFEST_NAME}"


def _scope_folders(cwd: Path, home: Path) -> list[tuple[Path, ListScope]]:
    return [
        (home / ".claude" / "skills", "user"),
        (cwd / ".claude" / "skills", "project"),
        (cwd / ".agents" / "skills", "agents"),
    ]


def _listed(folder: Path, scope: ListScope, record: InstallRecord | None) -> ListedSkill:
    origin = record.origin if record is not None else "unknown"
    try:
        manifest = Manifest.model_validate_json((folder / MANIFEST_NAME).read_bytes())
    except (OSError, ValidationError, ValueError):
        return ListedSkill(
            name=folder.name, path=str(folder), scope=scope, origin=origin, problem=UNREADABLE
        )
    src = manifest.source
    return ListedSkill(
        name=manifest.name,
        path=str(folder),
        scope=scope,
        origin=origin,
        title=src.title,
        author=src.author,
        platform=src.platform,
        url=src.canonical_url or src.url,
        extracted_at=manifest.extracted_at,
        confidence=manifest.confidence,
        critic_score=manifest.critic_score,
    )


def scan(cwd: Path, home: Path) -> ListResult:
    records: dict[Path, InstallRecord] = {}
    for r in installs.load().installs:
        path = installs.resolved(r.path)
        if path is not None:
            records[path] = r
    found: dict[Path, ListScope] = {}
    for parent, scope in _scope_folders(cwd, home):
        if not parent.is_dir():
            continue
        for child in sorted(parent.iterdir()):
            if (child / MANIFEST_NAME).is_file():
                found.setdefault(child.resolve(), scope)
    for path, record in records.items():
        if path.is_dir():
            found.setdefault(path, record.scope)
    skills = [_listed(path, scope, records.get(path)) for path, scope in found.items()]
    skills.sort(key=lambda s: (s.name, s.scope, s.path))
    return ListResult(skills=skills)


def locate(token: str, cwd: Path, home: Path) -> Path:
    """A skill folder from a path or an installed skill's name."""
    as_path = cwd / token
    if (as_path / MANIFEST_NAME).is_file():
        return as_path
    matches = [s for s in scan(cwd, home).skills if s.name == token]
    if not matches:
        raise SkipwatchError(
            ExitCode.UNSUPPORTED_SOURCE,
            f"no installed SkipWatch skill named {token}; /skipwatch list shows them",
        )
    if len(matches) > 1:
        paths = ", ".join(s.path for s in matches)
        raise SkipwatchError(
            ExitCode.USAGE, f"several skills are named {token}: {paths}; pass the path instead"
        )
    return Path(matches[0].path)
