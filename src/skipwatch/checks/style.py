"""8.7.6 style: no forbidden character or phrase in generated prose. Quotes are exempt."""

from pathlib import Path

from skipwatch.checks.runner import CheckContext, skill_files
from skipwatch.models import CheckItem, CheckResult
from skipwatch.skillmd import prose_spans

NAMED = {"em-dash": "\u2014", "en-dash": "\u2013"}
# Transcripts are verbatim speech, not generated prose.
EXEMPT = {"references/transcript.md"}


def _prose_files(staging: Path) -> list[Path]:
    """SKILL.md, then every .md under references/ and assets/ except the transcript."""
    files = []
    for path in skill_files(staging):
        rel = path.relative_to(staging)
        in_scope = rel.suffix.lower() == ".md" and rel.parts[0] in ("references", "assets")
        if in_scope and rel.as_posix() not in EXEMPT:
            files.append(path)
    skill_md = staging / "SKILL.md"
    return ([skill_md] if skill_md.is_file() else []) + files


def _texts(ctx: CheckContext) -> list[tuple[str, str]]:
    """(where, prose) pairs: the description, then each prose file."""
    description = ctx.doc.frontmatter.get("description")
    texts = [("the description", description)] if isinstance(description, str) else []
    for path in _prose_files(ctx.staging):
        rel = path.relative_to(ctx.staging).as_posix()
        mode = "procedure" if rel == "SKILL.md" else "all"
        text = path.read_bytes().decode("utf-8", errors="replace")
        texts.append((f"prose of {rel}", "\n".join(prose_spans(text, mode))))
    return texts


def run(ctx: CheckContext) -> CheckResult:
    items: list[CheckItem] = []
    for where, prose in _texts(ctx):
        for entry in ctx.config.style.forbid:
            needle = NAMED.get(entry, entry)
            label = entry if entry in NAMED else f"'{entry}'"
            n = prose.count(needle)
            if n:
                items.append(
                    CheckItem(
                        msg=f"{label} in {where} ({n} time{'s' if n > 1 else ''})",
                        fix="rewrite with a comma, colon, period or parentheses"
                        if entry in NAMED
                        else f"rephrase without '{entry}'",
                    )
                )
    return CheckResult(check="style", ok=not items, items=items)
