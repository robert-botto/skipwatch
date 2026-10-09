"""8.7.4 redaction (R-CHK-2 second half, plan issue 2). Applied in place.

Symlinks are never read, written or followed (structure fails on them). Text that is not valid
UTF-8 is decoded with replacement characters, redacted and written back as UTF-8. Binary files
cannot be edited safely, so a provider key inside one fails the check, as does a secret in a
file name (flagged, never renamed). The report names kinds and files, never values.
"""

from skipwatch.checks.runner import CheckContext, skill_files, write_atomic
from skipwatch.manifest import MANIFEST_NAME
from skipwatch.models import CheckItem, CheckResult
from skipwatch.redact import has_provider_key, redact_text

# Images and media may be binary; their bytes are still scanned for provider keys.
MEDIA_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov", ".wav", ".mp3", ".m4a"}
ARCHIVE_SUFFIXES = {".zip", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".tar"}
# Only these (and files with no suffix) are re-encoded when they are not valid UTF-8; anything
# else that is not UTF-8 is binary, and a PDF is always binary.
TEXT_SUFFIXES = {
    "",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".sh",
    ".py",
    ".js",
    ".ts",
    ".css",
    ".html",
    ".csv",
}
NON_TEXT_SUFFIXES = {".pdf"}
BOMS = [
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\xfe\xff", "utf-16-be"),
    (b"\xff\xfe", "utf-16-le"),
]


def wide_text_encoding(data: bytes) -> str | None:
    """UTF-16/32 by byte order mark, or UTF-16 by NULs on alternate bytes (ASCII-heavy text)."""
    for bom, encoding in BOMS:
        if data.startswith(bom):
            return encoding
    sample = data[:4096]
    if len(sample) < 4 or len(sample) % 2:
        return None
    even, odd = sample[0::2], sample[1::2]
    if even.count(0) == 0 and odd.count(0) >= 0.9 * len(odd):
        return "utf-16-le"
    if odd.count(0) == 0 and even.count(0) >= 0.9 * len(even):
        return "utf-16-be"
    return None


def _is_text(data: bytes, suffix: str) -> bool:
    """Valid UTF-8 is text whatever the suffix; invalid UTF-8 only for known text types."""
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return suffix in TEXT_SUFFIXES
    return True


def _decode_wide(data: bytes, encoding: str) -> str:
    text = data.decode(encoding, errors="replace")
    return text[1:] if text.startswith("\ufeff") else text


def _secret_frame_ids(ctx: CheckContext) -> list[str]:
    """Frames whose reader verbatim text changes under redaction showed a secret."""
    ids: list[str] = []
    for notes in ctx.notes:
        for frame in notes.frames:
            if frame.id not in ids and any(redact_text(v.text)[1] for v in frame.verbatim):
                ids.append(frame.id)
    return sorted(ids)


def run(ctx: CheckContext) -> CheckResult:
    items: list[CheckItem] = []
    ok = True
    removed: list[str] = []
    for frame_id in _secret_frame_ids(ctx):
        jpeg = ctx.staging / "assets" / "frames" / f"{frame_id}.jpg"
        if jpeg.is_file() and not jpeg.is_symlink():
            jpeg.unlink()
            removed.append(f"assets/frames/{frame_id}.jpg")
            items.append(CheckItem(msg=f"removed frame {frame_id} (showed a secret)"))

    for path in skill_files(ctx.staging):
        rel = path.relative_to(ctx.staging).as_posix()
        safe_rel, name_reps = redact_text(rel)
        if name_reps:
            ok = False
            items.append(
                CheckItem(
                    msg=f"file name contains a secret: {safe_rel}", fix="rename the file by hand"
                )
            )
        if rel == MANIFEST_NAME:
            continue
        if path.lstat().st_nlink > 1:
            # Never touch a file shared with something outside the skill; structure fails it.
            ok = False
            items.append(CheckItem(msg=f"{safe_rel} is a hardlink; not redacted"))
            continue
        suffix = path.suffix.lower()
        if suffix in ARCHIVE_SUFFIXES:
            ok = False
            items.append(CheckItem(msg=f"{safe_rel}: archives are not allowed in skills"))
            continue
        data = path.read_bytes()
        if suffix in MEDIA_SUFFIXES:
            if has_provider_key(data.decode("latin-1")):
                ok = False
                items.append(
                    CheckItem(msg=f"{safe_rel} is binary and contains a secret; remove the file")
                )
            continue
        wide = wide_text_encoding(data) if suffix in TEXT_SUFFIXES else None
        if suffix in NON_TEXT_SUFFIXES or (wide is None and not _is_text(data, suffix)):
            ok = False
            items.append(
                CheckItem(
                    msg=f"{safe_rel} is binary; only images and media may be binary in a skill"
                )
            )
            continue
        original = _decode_wide(data, wide) if wide else data.decode("utf-8", errors="replace")
        text = original
        if removed and suffix == ".md":
            lines = text.splitlines(keepends=True)
            text = "".join(line for line in lines if not any(ref in line for ref in removed))
        text, reps = redact_text(text)
        encoded = text.encode("utf-8")
        if encoded != data:
            write_atomic(path, encoded)
        if wide:
            items.append(CheckItem(msg=f"re-encoded {safe_rel} from {wide.upper()} to UTF-8"))
        elif original.encode("utf-8") != data:
            items.append(CheckItem(msg=f"re-encoded {safe_rel}"))
        for rep in reps:
            if rep.kind == "split_key":
                ok = False
                items.append(
                    CheckItem(
                        msg=f"{safe_rel}: a key may be split across lines; "
                        "join it and run check again"
                    )
                )
                continue
            items.append(
                CheckItem(
                    msg=f"replaced {rep.count} {rep.kind} with {rep.placeholder} in {safe_rel}"
                )
            )
    return CheckResult(check="redaction", ok=ok, items=items)
