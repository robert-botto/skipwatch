"""Skill packs (R-MAN-1, plan M5-C): a deterministic stored zip of an installed skill folder.

A pack holds `<name>/<posix relative path>` entries, sorted, with fixed dates and modes, and
the skill's own skipwatch.json, whose `files` lists a sha256 per other file. Packing refuses
a skill whose files no longer match those hashes; unpacking refuses anything unsafe or
mismatched (exit 9) before a byte is written.
"""

import hashlib
import io
import os
import re
import shutil
import stat
import unicodedata
import zipfile
import zlib
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from skipwatch.config import skipwatch_home
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.manifest import MANIFEST_NAME
from skipwatch.models import (
    IngestBundle,
    Manifest,
    PackOrigin,
    PackResult,
    Route,
    Segment,
    SourceInfo,
    Transcript,
    UnpackResult,
)
from skipwatch.project import PACK_SUFFIX
from skipwatch.workdir import WorkDir, write_model

ZIP_DATE = (1980, 1, 1, 0, 0, 0)
IGNORED_NAMES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})
MAX_FILES = 200
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024
MAX_PACK_BYTES = 26 * 1024 * 1024
NAME_RULE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")  # and len <= 64
NAME_MAX = 64
MAX_DEFLATE_RATIO = 100
LAST_SEGMENT_S = 15.0
TRANSCRIPT_REL = "references/transcript.md"


def _integrity(message: str) -> SkipwatchError:
    return SkipwatchError(ExitCode.PACK_INTEGRITY, message)


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def valid_name(name: str) -> bool:
    return len(name) <= NAME_MAX and NAME_RULE.match(name) is not None


WINDOWS_DEVICES = frozenset(
    {"CON", "PRN", "AUX", "NUL"} | {f"{kind}{n}" for kind in ("COM", "LPT") for n in "123456789"}
)
WINDOWS_FORBIDDEN = frozenset('<>"|?*')


def _unportable(part: str) -> bool:
    device = part.split(".")[0].upper() in WINDOWS_DEVICES
    return device or part.endswith((".", " ")) or any(c in WINDOWS_FORBIDDEN for c in part)


def path_problem(rel: str) -> str | None:
    """Why a relative entry path is unsafe or unportable, or None. Shared by pack and unpack
    so a pack SkipWatch writes is always one it would read."""
    if not rel.isprintable():
        return "name has a control character"
    if unicodedata.normalize("NFC", rel) != rel:
        return "name is not NFC"
    if "\\" in rel or ":" in rel:
        return "name has a backslash or colon"
    if rel.startswith("/"):
        return "absolute name"
    parts = rel.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return "empty, . or .. path part"
    if any(_unportable(part) for part in parts):
        return "name is not portable (a Windows device name or character)"
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


# ---- unpack ----


def _refuse(reason: str) -> SkipwatchError:
    return _integrity(f"pack integrity: {reason}")


def _shown(name: str) -> str:
    return name if name.isprintable() else repr(name)


def _entry_problem(info: zipfile.ZipInfo) -> str | None:
    if info.flag_bits & 0x1:
        return "encrypted"
    if info.orig_filename.endswith("/") or info.is_dir():
        return "directory entry"
    if (info.external_attr >> 16) & 0o170000 not in (0, 0o100000):
        return "not a regular file (symlink or special)"
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        return "unsupported compression"
    if info.file_size > MAX_FILE_BYTES:
        return f"over the {_mib(MAX_FILE_BYTES)} file limit"
    if info.compress_type == zipfile.ZIP_DEFLATED and info.file_size > MAX_DEFLATE_RATIO * max(
        info.compress_size, 1
    ):
        return f"compression ratio over {MAX_DEFLATE_RATIO}"
    return path_problem(info.orig_filename)


def _layout(infos: list[zipfile.ZipInfo]) -> str:
    """The one top folder every entry sits under, after checking each entry header."""
    if len(infos) > MAX_FILES:
        raise _refuse(f"more than {MAX_FILES} files")
    tops: set[str] = set()
    seen: set[str] = set()
    for info in infos:
        name = info.orig_filename
        problem = _entry_problem(info)
        if problem:
            raise _refuse(f"{_shown(name)}: {problem}")
        top, _, rel = name.partition("/")
        if not rel:
            raise _refuse(f"{_shown(name)}: not inside the skill folder")
        if name.casefold() in seen:
            raise _refuse(f"{_shown(rel)}: duplicate name (or one differing only in case)")
        seen.add(name.casefold())
        tops.add(top)
    if len(tops) != 1:
        raise _refuse("entries under more than one folder (a pack has one top folder only)")
    name = tops.pop()
    if not valid_name(name):
        raise _refuse(f"{_shown(name)}: folder name is not lowercase words joined by hyphens")
    if sum(info.file_size for info in infos) > MAX_TOTAL_BYTES:
        raise _refuse(f"over the {_mib(MAX_TOTAL_BYTES)} total limit")
    return name


def _read_entries(z: zipfile.ZipFile, infos: list[zipfile.ZipInfo]) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for info in infos:
        rel = info.orig_filename.partition("/")[2]
        try:
            with z.open(info) as f:
                data = f.read(MAX_FILE_BYTES + 1)
        except (zipfile.BadZipFile, zlib.error, OSError, EOFError, ValueError) as exc:
            raise _refuse(f"{_shown(rel)}: cannot be read ({type(exc).__name__})") from exc
        if len(data) != info.file_size:
            raise _refuse(f"{_shown(rel)}: size does not match its header")
        files[rel] = data
    return files


def _manifest_problems(files: dict[str, bytes], manifest: Manifest) -> list[str]:
    problems: dict[str, str] = {}
    for rel, data in files.items():
        expected = manifest.files.get(rel)
        if expected is None:
            problems[rel] = f"{_shown(rel)}: not in manifest"
        elif _sha256(data) != expected:
            problems[rel] = f"{rel}: hash mismatch"
    for rel in manifest.files:
        if rel not in files:
            problems[rel] = f"{_shown(rel)}: missing"
    return [problems[rel] for rel in sorted(problems)]


def _parse_pack(data: bytes) -> tuple[str, dict[str, bytes], Manifest, bytes]:
    """(name, files without skipwatch.json, manifest, manifest bytes) of verified pack bytes."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            name = _layout(infos)
            files = _read_entries(z, infos)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, ValueError, EOFError) as exc:
        raise _refuse("not a zip file, or a damaged one") from exc
    manifest_bytes = files.pop(MANIFEST_NAME, None)
    if manifest_bytes is None:
        raise _refuse(f"{MANIFEST_NAME} is missing")
    try:
        manifest = Manifest.model_validate_json(manifest_bytes)
    except ValidationError as exc:
        raise _refuse(f"{MANIFEST_NAME} is not valid") from exc
    if manifest.name != name:
        raise _refuse(f"{MANIFEST_NAME} names {_shown(manifest.name)} but the folder is {name}")
    problems = _manifest_problems(files, manifest)
    if problems:
        raise _refuse("; ".join(problems))
    return name, files, manifest, manifest_bytes


def _pack_bytes(path: Path) -> bytes:
    try:
        size = path.stat().st_size
        if size > MAX_PACK_BYTES:
            raise _refuse(f"pack is over the {_mib(MAX_PACK_BYTES)} pack limit")
        with path.open("rb") as f:
            data = f.read(MAX_PACK_BYTES + 1)
    except OSError as exc:
        raise _refuse(f"cannot read {path.name}: {exc.strerror or exc}") from exc
    if len(data) > MAX_PACK_BYTES:  # it grew after stat
        raise _refuse(f"pack is over the {_mib(MAX_PACK_BYTES)} pack limit")
    return data


def read_pack(path: Path) -> tuple[str, dict[str, bytes], Manifest]:
    """(name, {rel: bytes} without skipwatch.json, manifest). Every refusal is PACK_INTEGRITY
    with a one-line reason; nothing is written."""
    name, files, manifest, _ = _parse_pack(_pack_bytes(path))
    return name, files, manifest


_TIMED_LINE = re.compile(r"^\[(?:(\d+):)?(\d+):([0-5]\d)\]\s*(.*?)\s*$")


def transcript_from_markdown(text: str) -> Transcript | None:
    """'[mm:ss] text' or '[h:mm:ss] text' lines -> segments (end = next start, last +15 s);
    None when no line parses. origin 'pack'."""
    timed: list[tuple[float, str]] = []
    for line in text.splitlines():
        match = _TIMED_LINE.match(line.strip())
        if not match or not match.group(4):
            continue
        hours, minutes, seconds, words = match.groups()
        if hours is not None and int(minutes) > 59:
            continue
        start = int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)
        timed.append((float(start), words))
    if not timed:
        return None
    segments = []
    for n, (start, words) in enumerate(timed):
        end = timed[n + 1][0] if n + 1 < len(timed) else start + LAST_SEGMENT_S
        segments.append(Segment(start=start, end=max(start, end), text=words))
    return Transcript(origin="pack", segments=segments)


def _packs_dir() -> Path:
    """$SKIPWATCH_HOME/packs, resolved: check (M5-B) requires a pack work folder whose parent
    is exactly this path."""
    return (skipwatch_home() / "packs").resolve()


def _claim_work(name: str, now: datetime) -> Path:
    base = _packs_dir() / f"{name}-{now:%Y%m%d-%H%M%S}"
    for n in range(1000):
        path = base if n == 0 else base.with_name(f"{base.name}-{n}")
        try:
            path.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        return path
    raise SkipwatchError(ExitCode.USAGE, f"too many pack work folders named {base.name}")


WORK_RULE = "--work must be a new folder directly under $SKIPWATCH_HOME/packs/"


def _given_work(work: Path) -> Path:
    packs = _packs_dir()
    work = work.absolute()
    if work.name in ("", ".", "..") or work.parent.resolve() != packs:
        raise SkipwatchError(ExitCode.USAGE, f"{WORK_RULE} ({packs}); got {work}")
    folder = packs / work.name
    packs.mkdir(parents=True, exist_ok=True)
    try:
        folder.mkdir(exist_ok=False)
    except FileExistsError:
        raise SkipwatchError(ExitCode.USAGE, f"{WORK_RULE}; {folder} already exists") from None
    return folder


def _write_staging(staging: Path, files: dict[str, bytes]) -> None:
    root = staging.resolve()
    for rel, data in files.items():
        path = staging.joinpath(*rel.split("/"))
        if not path.resolve().is_relative_to(root):  # never, after path_problem
            raise _refuse(f"{_shown(rel)}: outside the skill folder")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as f:
            f.write(data)


def _ingest(manifest: Manifest, origin: PackOrigin) -> IngestBundle:
    src = manifest.source
    return IngestBundle(
        source=SourceInfo(
            kind="file" if src.platform == "local" else "video",
            platform=src.platform,
            url=src.url,
            canonical_url=src.canonical_url,
            author=src.author,
            title=src.title,
            posted_at=src.posted_at,
        ),
        route=Route(context="pack"),
        fetched_with_cookies=False,
        pack=origin,
    )


def unpack(
    source: Path,
    work: Path | None,
    *,
    fetched_from: str | None = None,
    now: datetime | None = None,
) -> UnpackResult:
    """Verify, then lay out <work>/staging/<name>/ and the synthetic ingest.json and
    transcript.json. Nothing is written until the whole pack has been verified."""
    data = _pack_bytes(source)
    name, files, manifest, manifest_bytes = _parse_pack(data)
    if manifest.fetched_with_cookies:
        raise SkipwatchError(
            ExitCode.PRIVATE_CONTENT,
            "This pack was made from content fetched with someone's browser cookies; "
            "SkipWatch does not unpack it.",
        )
    folder = _given_work(work) if work is not None else _claim_work(name, now or datetime.now())
    try:
        staging = folder / "staging" / name
        staging.mkdir(parents=True, exist_ok=True)
        _write_staging(staging, {**files, MANIFEST_NAME: manifest_bytes})
        WorkDir(folder).ensure()
        origin = PackOrigin(
            file=fetched_from or source.name, sha256=_sha256(data), manifest=manifest
        )
        write_model(folder / "ingest.json", _ingest(manifest, origin))
        transcript_md = files.get(TRANSCRIPT_REL)
        transcript = (
            transcript_from_markdown(transcript_md.decode("utf-8", errors="replace"))
            if transcript_md is not None
            else None
        )
        if transcript is not None:
            write_model(folder / "transcript.json", transcript)
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return UnpackResult(
        name=name,
        work=str(folder),
        staging=str(staging),
        pack_sha256=origin.sha256,
        files=len(files) + 1,
        fetched_from=fetched_from,
        claimed_confidence=manifest.confidence,
        claimed_critic_score=manifest.critic_score,
        transcript=transcript is not None,
    )
