"""8.7.3 provenance (R-DIS-2, R-DIS-3): one tag per step, quotes traceable to their source.

[spoken] quotes match the transcript after NFKC, quote folding, case and whitespace
normalisation, on word boundaries, and must be at least 3 words or 12 characters. [on-screen]
quotes follow the same length rule; for commands, settings and prompts they must be the whole
reader item or whole lines of it, for other text they sit inside it on word boundaries. The
[illegible at mm:ss] wildcard covers at most 40 characters on one line and needs a reader
`illegible` entry within the window. Indented code, <pre> and inline code in the action are
quotes too. [written] quotes must come from the post, thread or links.
"""

import re
import unicodedata

from skipwatch.checks.runner import CheckContext
from skipwatch.models import CheckItem, CheckResult, VerbatimItem
from skipwatch.redact import redact_text
from skipwatch.skillmd import Step, Tag

WINDOW_S = 20.0
MIN_WORDS = 3
MIN_CHARS = 12
ILLEGIBLE = re.compile(r"\[illegible at \d{1,2}:\d{2}(?::\d{2})?\]")
# The [illegible] wildcard stands for at most 40 characters on one line.
WILDCARD = r"[^\n]{0,40}?"
WHOLE_KINDS = {"command", "setting", "prompt"}
QUOTE_FOLD = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u2032": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
        "\u2033": '"',
    }
)
# "Step 4: <reason of 3+ words>" as its own line or list item under Unverified and gaps.
INFERRED_LINE = r"(?im)^\s*(?:[-*]\s+|\d+\.\s+)?step\s+{n}\s*[:\-]\s*\S+(?:\s+\S+){{2,}}"


def mmss(seconds: float) -> str:
    s = max(0, int(seconds))
    if s >= 3600:
        return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}"
    return f"{s // 60:02d}:{s % 60:02d}"


def _norm(text: str) -> str:
    """NFKC, curly quotes folded to straight, lower case, whitespace collapsed."""
    text = unicodedata.normalize("NFKC", text).translate(QUOTE_FOLD)
    return " ".join(text.lower().split())


def _contains_words(haystack: str, quote: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(quote) + r"(?!\w)", haystack) is not None


def _too_short(quote: str) -> bool:
    return len(quote.split()) < MIN_WORDS and len(quote) < MIN_CHARS


def _fix(t: float) -> str:
    return f"re-read {mmss(t - WINDOW_S)} to {mmss(t + WINDOW_S)}"


def _spoken_items(ctx: CheckContext, step: Step, tag: Tag) -> list[CheckItem]:
    assert tag.seconds is not None
    t = tag.seconds
    label = f"[spoken {mmss(t)}]"
    if ctx.transcript is None:
        return [
            CheckItem(step=step.number, msg=f"{label} but the work folder has no transcript.json")
        ]
    heard = _norm(
        " ".join(
            s.text
            for s in ctx.transcript.segments
            if s.end >= t - WINDOW_S and s.start <= t + WINDOW_S
        )
    )
    items = []
    for quote in step.quotes + step.code_quotes:
        q = _norm(quote)
        if _too_short(q):
            items.append(CheckItem(step=step.number, msg=f"{label} quote is too short to verify"))
        elif not _contains_words(heard, q):
            items.append(
                CheckItem(
                    step=step.number,
                    msg=f"{label} quote not found in transcript within {WINDOW_S:.0f} s",
                    fix=_fix(t),
                )
            )
    return items


def _screen_line(text: str) -> str:
    return " ".join(text.split())


def _screen_lines(text: str) -> list[str]:
    return [_screen_line(line) for line in redact_text(text)[0].splitlines() if line.strip()]


def _wild_pattern(quote_line: str) -> str:
    parts = [re.escape(_screen_line(p)) for p in ILLEGIBLE.split(quote_line)]
    return WILDCARD.join(parts)


def _line_matches(quote_line: str, seen_line: str, whole: bool) -> bool:
    """One quote line against one note line: equal when whole, else on word boundaries."""
    if ILLEGIBLE.search(quote_line):
        pattern = _wild_pattern(quote_line)
    else:
        pattern = re.escape(_screen_line(quote_line))
    if whole:
        return re.fullmatch(pattern, seen_line) is not None
    return re.search(r"(?<!\w)" + pattern + r"(?!\w)", seen_line) is not None


def _screen_matches(quote: str, item: VerbatimItem) -> bool:
    """Commands, settings and prompts: the quote is the whole item or whole lines of it.
    Other text: the quote sits inside the item on word boundaries."""
    q_lines = _screen_lines(quote)
    seen = _screen_lines(item.text)
    if not q_lines or not seen:
        return False
    if item.kind in WHOLE_KINDS:
        n = len(q_lines)
        return any(
            all(
                _line_matches(q, s, whole=True)
                for q, s in zip(q_lines, seen[k : k + n], strict=True)
            )
            for k in range(len(seen) - n + 1)
        )
    joined = " ".join(seen)
    return _line_matches(" ".join(q_lines), joined, whole=False)


def _screen_items(ctx: CheckContext, step: Step, tag: Tag) -> list[CheckItem]:
    assert tag.seconds is not None
    t = tag.seconds
    label = f"[on-screen {mmss(t)}]"
    frames = [
        frame for notes in ctx.notes for frame in notes.frames if abs(frame.t - t) <= WINDOW_S
    ]
    items = []
    for quote in step.quotes + step.code_quotes:
        literal = _screen_line(ILLEGIBLE.sub(" ", quote))
        if _too_short(literal):
            items.append(CheckItem(step=step.number, msg=f"{label} quote is too short to verify"))
            continue
        wild = ILLEGIBLE.search(quote)
        if wild and ("\n" in quote.strip() or not any(frame.illegible for frame in frames)):
            items.append(
                CheckItem(
                    step=step.number,
                    msg=f"{label} [illegible] needs a one-line quote and a reader "
                    "illegible entry within 20 s",
                    fix=_fix(t),
                )
            )
            continue
        if not any(_screen_matches(quote, item) for frame in frames for item in frame.verbatim):
            items.append(
                CheckItem(
                    step=step.number,
                    msg=f"{label} quote not found in frame notes within {WINDOW_S:.0f} s",
                    fix=_fix(t),
                )
            )
    return items


def _written_items(ctx: CheckContext, step: Step) -> list[CheckItem]:
    context = ctx.ingest.context
    sources = [context.post_text or "", *context.thread, *context.author_replies]
    sources += [link.text for link in context.links]
    written = _norm(" \n ".join(sources))
    return [
        CheckItem(step=step.number, msg="[written] quote not found in the post, thread or links")
        for quote in step.quotes
        if not _norm(quote) or not _contains_words(written, _norm(quote))
    ]


def _listed_in_gaps(ctx: CheckContext, number: int) -> bool:
    gaps = ctx.doc.section_text("Unverified and gaps")
    return re.search(INFERRED_LINE.format(n=number), gaps) is not None


def _step_items(ctx: CheckContext, step: Step) -> list[CheckItem]:
    if not step.tags:
        return [CheckItem(step=step.number, msg="step has no provenance tag")]
    if len(step.tags) > 1:
        return [
            CheckItem(
                step=step.number,
                msg=f"step has {len(step.tags)} provenance tags; exactly one is allowed",
            )
        ]
    tag = step.tags[0]
    if tag.kind in ("spoken", "on-screen") and not (step.quotes or step.code_quotes):
        assert tag.seconds is not None
        return [
            CheckItem(
                step=step.number,
                msg=f"[{tag.kind} {mmss(tag.seconds)}] step has no quote block",
                fix="add the exact words as a > quote or fenced block",
            )
        ]
    if tag.kind == "spoken":
        return _spoken_items(ctx, step, tag)
    if tag.kind == "on-screen":
        return _screen_items(ctx, step, tag)
    if tag.kind == "written":
        return _written_items(ctx, step)
    if not _listed_in_gaps(ctx, step.number):
        return [
            CheckItem(
                step=step.number,
                msg="[inferred] step is not listed under Unverified and gaps",
                fix=f"add 'Step {step.number}: <reason>' under Unverified and gaps",
            )
        ]
    return []


def run(ctx: CheckContext) -> CheckResult:
    items = [item for step in ctx.doc.steps for item in _step_items(ctx, step)]
    return CheckResult(check="provenance", ok=not items, items=items)
