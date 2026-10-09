"""8.7.2 structure (R-SK-3): sections in order, size, referenced files, manifest, frame cap."""

import os
import re
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

from pydantic import ValidationError

from skipwatch.checks.runner import CheckContext, skill_entries
from skipwatch.models import CheckItem, CheckResult, Manifest

REQUIRED_SECTIONS = (
    "What this does",
    "Prerequisites",
    "Procedure",
    "Decision points",
    "Gotchas",
    "Verification",
    "Worked example",
    "Unverified and gaps",
    "Attribution",
)
ATTRIBUTION_PHRASES = ("with SkipWatch", "The workflow and wording are the creator's")
MAX_LINES = 500  # SKILL.md must stay under this (R-SK-3)
MAX_FRAMES = 8
LINK = re.compile(r"\]\((<[^>]*>|[^)\s]+)(?:\s+\"[^\"]*\")?\)")
BACKTICK_PATH = re.compile(r"`((?:references|assets|scripts)/[^`\s]+)`")
REF_DEF = re.compile(r"(?m)^\s{0,3}\[[^\]]+\]:\s*(\S+)")
IMG_SRC = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
# Web links and in-page anchors are not files. Every other target must stay inside the skill.
WEB = re.compile(r"^(?:https?:|mailto:|#)", re.IGNORECASE)


def _section_items(ctx: CheckContext) -> list[CheckItem]:
    doc = ctx.doc
    items: list[CheckItem] = []
    if not any(s.level == 1 for s in doc.sections):
        items.append(CheckItem(msg="missing H1 title"))
    h2 = [s.title for s in doc.sections if s.level == 2]
    for title in REQUIRED_SECTIONS:
        if title not in h2:
            items.append(CheckItem(msg=f"missing section: {title}", fix=f"add '## {title}'"))
    for title in h2:
        if title not in REQUIRED_SECTIONS:
            items.append(CheckItem(msg=f"unexpected section: {title}"))
    present = [t for t in h2 if t in REQUIRED_SECTIONS]
    expected = [t for t in REQUIRED_SECTIONS if t in present]
    if present != expected or len(present) != len(set(present)):
        items.append(
            CheckItem(
                msg="sections out of order: " + ", ".join(present),
                fix="order: " + ", ".join(REQUIRED_SECTIONS),
            )
        )
    if "Attribution" in h2:
        attribution = doc.section_text("Attribution")
        for phrase in ATTRIBUTION_PHRASES:
            if phrase not in attribution:
                items.append(CheckItem(msg=f'Attribution must say "{phrase}"'))
    return items


def _referenced_paths(text: str) -> list[str]:
    """Targets of inline links, reference definitions, <img src> and backticked skill paths."""
    paths: list[str] = []
    targets = (
        LINK.findall(text)
        + REF_DEF.findall(text)
        + IMG_SRC.findall(text)
        + BACKTICK_PATH.findall(text)
    )
    for target in targets:
        target = target.strip().removeprefix("<").removesuffix(">")
        if WEB.match(target):
            continue
        target = target.split("#", 1)[0]
        if target and target not in paths:
            paths.append(target)
    return paths


def _plain(rel: str) -> str:
    """The path a reader would open: percent-decoded, backslashes as separators."""
    return unquote(rel).replace("\\", "/")


def _inside(staging: Path, rel: str) -> bool:
    """True if rel is a plain relative path that resolves inside staging."""
    plain = _plain(rel)
    if re.match(r"^(?:[a-z][a-z0-9+.-]*:|/|~|[A-Za-z]:)", plain, re.IGNORECASE):
        return False
    root = staging.resolve()
    return (root / plain).resolve().is_relative_to(root)


def _exists_exactly(staging: Path, rel: str) -> bool:
    """Exists with exactly this spelling, so References/Source.md fails even on macOS."""
    current = staging
    for part in PurePosixPath(_plain(rel)).parts:
        if part == ".":
            continue
        if part not in os.listdir(current):
            return False
        current = current / part
    return current.is_file()


def _reference_items(ctx: CheckContext) -> list[CheckItem]:
    items = []
    for rel in _referenced_paths(ctx.doc.body):
        if not _inside(ctx.staging, rel):
            items.append(CheckItem(msg=f"reference escapes the skill folder: {rel}"))
        elif not _exists_exactly(ctx.staging, rel):
            items.append(CheckItem(msg=f"referenced file missing: {rel}"))
    return items


def run(ctx: CheckContext) -> CheckResult:
    skill_md = ctx.staging / "SKILL.md"
    if not skill_md.exists():
        return CheckResult(
            check="structure", ok=False, items=[CheckItem(msg="SKILL.md is missing")]
        )
    items = _section_items(ctx)
    if ctx.doc.line_count >= MAX_LINES:
        items.append(
            CheckItem(
                msg=f"SKILL.md has {ctx.doc.line_count} lines; it must stay under {MAX_LINES}",
                fix="move long material to references/ with a pointer line",
            )
        )
    items += _reference_items(ctx)
    files, links, specials = skill_entries(ctx.staging)
    for link in links:
        rel = link.relative_to(ctx.staging).as_posix()
        items.append(
            CheckItem(msg=f"symlink not allowed in a skill: {rel}", fix="copy the file in")
        )
    for path in files:
        if path.lstat().st_nlink > 1:
            rel = path.relative_to(ctx.staging).as_posix()
            items.append(
                CheckItem(msg=f"hardlink not allowed in a skill: {rel}", fix="copy the file in")
            )
    for path in specials:
        rel = path.relative_to(ctx.staging).as_posix()
        items.append(CheckItem(msg=f"special file not allowed in a skill: {rel}"))

    manifest = ctx.staging / "skipwatch.json"
    if not manifest.exists():
        items.append(CheckItem(msg="skipwatch.json is missing"))
    else:
        try:
            Manifest.model_validate_json(manifest.read_text(encoding="utf-8"))
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(p) for p in first["loc"]) or "root"
            items.append(CheckItem(msg=f"skipwatch.json is not valid: {where}: {first['msg']}"))

    frames_dir = ctx.staging / "assets" / "frames"
    frames = [p for p in frames_dir.iterdir() if p.is_file()] if frames_dir.is_dir() else []
    if len(frames) > MAX_FRAMES:
        items.append(
            CheckItem(msg=f"{len(frames)} frames in assets/frames; the cap is {MAX_FRAMES}")
        )
    return CheckResult(check="structure", ok=not items, items=items)
