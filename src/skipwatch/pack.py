"""Skill packs (R-MAN-1, plan M5-C): a deterministic stored zip of an installed skill folder.

A pack holds `<name>/<posix relative path>` entries, sorted, with fixed dates and modes, and
the skill's own skipwatch.json, whose `files` lists a sha256 per other file. Packing refuses
a skill whose files no longer match those hashes; unpacking refuses anything unsafe or
mismatched (exit 9) before a byte is written.
"""

import hashlib
import os
import re
import stat
import unicodedata
import zipfile
from pathlib import Path

from pydantic import ValidationError

from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.manifest import MANIFEST_NAME
from skipwatch.models import Manifest, PackResult
from skipwatch.project import PACK_SUFFIX

ZIP_DATE = (1980, 1, 1, 0, 0, 0)
IGNORED_NAMES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})
MAX_FILES = 200
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024
MAX_PACK_BYTES = 26 * 1024 * 1024
NAME_RULE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")  # and len <= 64
NAME_MAX = 64


def _integrity(message: str) -> SkipwatchError:
    return SkipwatchError(ExitCode.PACK_INTEGRITY, message)


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def valid_name(name: str) -> bool:
    return len(name) <= NAME_MAX and NAME_RULE.match(name) is not None


def path_problem(rel: str) -> str | None:
    """Why a relative entry path is unsafe or unportable, or None. Shared by pack and unpack
    so a pack SkipWatch writes is always one it would read."""
    if unicodedata.normalize("NFC", rel) != rel:
        return "name is not NFC"
    if "\\" in rel or ":" in rel:
        return "name has a backslash or colon"
    if rel.startswith("/"):
        return "absolute name"
    if any(part in ("", ".", "..") for part in rel.split("/")):
        return "empty, . or .. path part"
    return None


def skill_tree(skill_dir: Path) -> tuple[dict[str, Path], list[str]]:
    """(posix relative path -> file, ignored names). Raises PACK_INTEGRITY on a symlink or
    special file. Symlinked folders are never followed."""
    files: dict[str, Path] = {}
    ignored: list[str] = []
    for top, dirs, names in os.walk(skill_dir, followlinks=False):
        for entry in sorted(dirs + names):
            path = Path(top) / entry
            rel = path.relative_to(skill_dir).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise _integrity(f"{rel}: symlinks cannot be packed")
            if stat.S_ISDIR(mode):
                continue
            if not stat.S_ISREG(mode):
                raise _integrity(f"{rel}: not a regular file")
            if entry in IGNORED_NAMES:
                ignored.append(rel)
            else:
                files[rel] = path
    return dict(sorted(files.items())), sorted(ignored)


def verify_files(skill_dir: Path, manifest: Manifest) -> list[str]:
    """Problems, one per file: '<rel>: hash mismatch' | '<rel>: not in manifest' | '<rel>: missing'.
    skipwatch.json and IGNORED_NAMES are not compared."""
    files, _ = skill_tree(skill_dir)
    files.pop(MANIFEST_NAME, None)
    problems: dict[str, str] = {}
    for rel, path in files.items():
        expected = manifest.files.get(rel)
        if expected is None:
            problems[rel] = f"{rel}: not in manifest"
        elif _sha256(path.read_bytes()) != expected:
            problems[rel] = f"{rel}: hash mismatch"
    for rel in manifest.files:
        if rel not in files:
            problems[rel] = f"{rel}: missing"
    return [problems[rel] for rel in sorted(problems)]


def _read_manifest(skill_dir: Path) -> tuple[Manifest, bytes]:
    try:
        raw = (skill_dir / MANIFEST_NAME).read_bytes()
        return Manifest.model_validate_json(raw), raw
    except (OSError, ValidationError) as exc:
        raise _integrity("skipwatch.json is missing or invalid; reinstall the skill") from exc


def _mib(n: int) -> str:
    return f"{n / (1024 * 1024):g} MiB"


def _check_limits(entries: dict[str, bytes]) -> None:
    if len(entries) > MAX_FILES:
        raise _integrity(f"more than {MAX_FILES} files")
    for rel, data in entries.items():
        problem = path_problem(rel)
        if problem:
            raise _integrity(f"{rel}: {problem}")
        if len(data) > MAX_FILE_BYTES:
            raise _integrity(f"{rel}: over the {_mib(MAX_FILE_BYTES)} file limit")
    folded = [rel.casefold() for rel in entries]
    if len(set(folded)) != len(folded):
        raise _integrity("two files whose names differ only in case")
    if sum(len(data) for data in entries.values()) > MAX_TOTAL_BYTES:
        raise _integrity(f"over the {_mib(MAX_TOTAL_BYTES)} total limit")


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=ZIP_DATE)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def pack_skill(skill_dir: Path, out: Path | None) -> PackResult:
    """Deterministic stored zip of an installed skill. out defaults to ./<name>.skillpack.zip."""
    skill_dir = skill_dir.resolve()
    manifest, manifest_bytes = _read_manifest(skill_dir)
    name = manifest.name
    if not valid_name(name):
        raise _integrity(f"skill name {name!r} is not lowercase words joined by hyphens")
    if manifest.fetched_with_cookies:
        raise SkipwatchError(
            ExitCode.PRIVATE_CONTENT,
            "This skill was made from content fetched with your browser cookies, "
            "so it cannot be packed for sharing.",
        )
    if not manifest.checks_passed:
        raise SkipwatchError(
            ExitCode.CHECK_FAILED, f"{name} did not pass its checks, so it cannot be packed"
        )
    problems = verify_files(skill_dir, manifest)
    if problems:
        raise _integrity(
            f"files changed since install: {'; '.join(problems)}; "
            "reinstall it from its work folder or run check again"
        )
    files, ignored = skill_tree(skill_dir)
    entries = {rel: path.read_bytes() for rel, path in files.items() if rel != MANIFEST_NAME}
    entries[MANIFEST_NAME] = manifest_bytes
    _check_limits(entries)
    out = (out if out is not None else Path.cwd() / f"{name}{PACK_SUFFIX}").absolute()
    tmp = out.with_name(out.name + ".tmp")
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED) as z:
            for entry in sorted(f"{name}/{rel}" for rel in entries):
                z.writestr(_zip_info(entry), entries[entry[len(name) + 1 :]])
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)
    data = out.read_bytes()
    return PackResult(
        name=name,
        path=str(out),
        sha256=_sha256(data),
        files=len(entries),
        bytes=len(data),
        ignored=ignored,
    )
