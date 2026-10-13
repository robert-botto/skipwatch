"""8.7.3 provenance (R-DIS-2, R-DIS-3): one tag per step, quotes traceable to their source.

[spoken] quotes match the transcript after NFKC, quote folding, case and whitespace
normalisation, on word boundaries, and must be at least 3 words or 12 characters. [on-screen]
quotes follow the same length rule, except a quote equal to a whole command, code, setting or
ui_path item (NFKC and whitespace, case kept; the quote itself already NFKC), which is valid at
any length; for commands, settings and
prompts they must be the whole reader item or whole lines of it, for other text they sit
inside it on word boundaries. The
[illegible at mm:ss] wildcard covers at most 40 characters on one line and needs a reader
`illegible` entry within the window. Indented code, <pre> and inline code in the action are
quotes too, for every tag. Short inline code in a [spoken] step (`.env`, `--force`) is
checked as speech: symbols become the words people say ("dot env", "dash dash force") on both
sides, and the words that say it must be inside the step's own quote. [written] quotes and
code must come from the post, thread or links.

Pack mode (ingest.pack set by unpack, nothing else): every structure rule above still holds and
[spoken] quotes are checked against the pack transcript; [on-screen] and [written] quotes, and
[spoken] ones when the pack has no transcript, are counted in one non-failing info item. A
`pack` field outside a real pack work folder fails provenance; it never runs as either mode.
"""

import re
import unicodedata

from skipwatch.checks.runner import CheckContext
from skipwatch.manifest import pack_refusal
from skipwatch.models import CheckItem, CheckResult, FrameNote, VerbatimItem
from skipwatch.redact import redact_text
from skipwatch.skillmd import Step, Tag

WINDOW_S = 20.0
MIN_WORDS = 3
MIN_CHARS = 12
ILLEGIBLE = re.compile(r"\[illegible at \d{1,2}:\d{2}(?::\d{2})?\]")
# The [illegible] wildcard stands for at most 40 characters on one line.
WILDCARD = r"[^\n]{0,40}?"
WHOLE_KINDS = {"command", "setting", "prompt"}
# A quote shorter than the minimum is still evidence when it is the whole reader item for these
# kinds: a one-word command such as `copilot` shown on its own is exactly what was on screen.
SHORT_WHOLE_KINDS = {"command", "code", "setting", "ui_path"}
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
# Symbols as speech-to-text writes them out. Only symbols inside a token count: a full stop
# that ends a sentence is never "dot".
SYMBOL_WORDS = {
    ".": "dot",
    "-": "dash",
    "_": "underscore",
    "/": "slash",
    "\\": "backslash",
    "~": "tilde",
    "@": "at",
    "#": "hash",
    "=": "equals",
    ":": "colon",
    "+": "plus",
    "*": "star",
    "$": "dollar",
    "|": "pipe",
    "%": "percent",
}
SPOKEN_SYNONYMS = [
    (re.compile(r"\bdouble dash\b"), "dash dash"),
    (re.compile(r"\b(?:hyphen|minus)\b"), "dash"),
    (re.compile(r"\bperiod\b"), "dot"),
    (re.compile(r"\bforward slash\b"), "slash"),
    (re.compile(r"\b(?:equal|equals) sign\b"), "equals"),
    (re.compile(r"\b(dollar|at) sign\b"), r"\1"),
]
TOKEN_EDGES = re.compile(r"^[\"'(\[]+|[.,!?;:\"')\]]+$")
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


def _contains_code(haystack: str, code: str) -> bool:
    """Code named whole in normalised text: whitespace, an opening bracket or quote, or the
    edge before it; whitespace, closing punctuation or the edge after it; and no flag running
    on, so `git push` is not cut from "git push --dry-run" nor `rm -rf build` from
    "rm -rf build/cache". Code that is not already NFKC (a full-width lookalike) never matches."""
    q = _norm(code)
    if not q or unicodedata.normalize("NFKC", code) != code:
        return False
    pattern = (
        r"(?:^|(?<=[\s(\[\"'`]))" + re.escape(q) + r"(?=$|\s|[.,;:!?)\]\"'`]+(?:\s|$))(?!\s+-\S)"
    )
    return re.search(pattern, haystack) is not None


def _too_short(quote: str) -> bool:
    return len(quote.split()) < MIN_WORDS and len(quote) < MIN_CHARS


def _spoken_form(text: str, code: bool = False) -> str:
    """Words as spoken: NFKC, lower case, symbols inside a token spelled out. Transcript tokens
    lose their sentence punctuation first. Code keeps every character, and code that is not
    already NFKC or holds a character with no spoken word (`;`, `>`, `!`, an invisible
    character) is unverifiable: "" never matches."""
    if code and (
        unicodedata.normalize("NFKC", text) != text
        or any(not (c.isalnum() or c.isspace() or c in SYMBOL_WORDS) for c in text)
    ):
        return ""
    words = []
    for token in unicodedata.normalize("NFKC", text).translate(QUOTE_FOLD).lower().split():
        if not code:
            token = TOKEN_EDGES.sub("", token)
        for part in re.findall(r"[^\W_]+|\S", token):
            if part[0].isalnum():
                words.append(part)
            elif part in SYMBOL_WORDS:
                words.append(SYMBOL_WORDS[part])
    spoken = " ".join(words)
    for pattern, repl in SPOKEN_SYNONYMS:
        spoken = pattern.sub(repl, spoken)
    return spoken


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
    short_inline = [code for code in step.inline_code if _too_short(_norm(code))]
    for code in short_inline:
        items += _short_inline_items(step, code, label, t)
    long_inline = [code for code in step.inline_code if code not in short_inline]
    for quote in step.quotes + step.code_quotes + long_inline:
        q = _norm(quote)
        if _too_short(q):
            # A short spoken quote is too weak alone (any common word is in some transcript).
            # When the screen shows it whole, the on-screen tag is the evidence that verifies.
            items.append(
                CheckItem(
                    step=step.number,
                    msg=f"{label} quote is too short to verify",
                    fix="if the screen shows this whole command, tag the step [on-screen mm:ss]",
                )
            )
        elif not _contains_words(heard, q):
            items.append(
                CheckItem(
                    step=step.number,
                    msg=f"{label} quote not found in transcript within {WINDOW_S:.0f} s",
                    fix=_fix(t),
                )
            )
    return items


def _short_inline_items(step: Step, code: str, label: str, t: float) -> list[CheckItem]:
    """Short inline code in the action (`.env`, `--force`): said inside the step's own quotes,
    which are themselves checked against the transcript, symbols compared as spoken words. The
    wider window is not evidence: a common short token is somewhere in any 40 s of speech."""
    shown = f"`{redact_text(code)[0]}`"
    if not step.quotes:
        return [
            CheckItem(
                step=step.number,
                msg=f"{label} inline code {shown} needs a > quote of the words that say it",
                fix=f"add the line that says it as a > quote; {_fix(t)}",
            )
        ]
    needle = _spoken_form(code, code=True)
    if needle and any(f" {needle} " in f" {_spoken_form(quote)} " for quote in step.quotes):
        return []
    return [
        CheckItem(
            step=step.number,
            msg=f"{label} inline code {shown} is not said in the step's quote",
            fix=f"{_fix(t)} and quote the line that says it as a > quote; if it is only shown, "
            "make it an [on-screen mm:ss] step; if it is neither said nor shown, tag the step "
            "[inferred] and list it under Unverified and gaps",
        )
    ]


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


def _exact(text: str) -> str:
    """NFKC and collapsed whitespace, case kept: `ls -r` is not `ls -R`."""
    return _screen_line(unicodedata.normalize("NFKC", redact_text(text)[0]))


def _is_whole_short_item(quote: str, frames: list[FrameNote]) -> bool:
    """The quote equals a whole command, code, setting or ui_path item, case kept. The quote
    itself must already be NFKC text, so a full-width lookalike never verifies."""
    if unicodedata.normalize("NFKC", quote) != quote:
        return False
    q = _exact(quote)
    return bool(q) and any(
        item.kind in SHORT_WHOLE_KINDS and _exact(item.text) == q
        for frame in frames
        for item in frame.verbatim
    )


def _screen_items(ctx: CheckContext, step: Step, tag: Tag) -> list[CheckItem]:
    assert tag.seconds is not None
    t = tag.seconds
    label = f"[on-screen {mmss(t)}]"
    frames = [
        frame for notes in ctx.notes for frame in notes.frames if abs(frame.t - t) <= WINDOW_S
    ]
    items = []
    for quote in step.quotes + step.code_quotes + step.inline_code:
        literal = _screen_line(ILLEGIBLE.sub(" ", quote))
        if _too_short(literal):
            if not ILLEGIBLE.search(quote) and _is_whole_short_item(quote, frames):
                continue
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
    missing = [q for q in step.quotes if not _norm(q) or not _contains_words(written, _norm(q))]
    missing += [c for c in step.code_quotes + step.inline_code if not _contains_code(written, c)]
    return [
        CheckItem(step=step.number, msg="[written] quote not found in the post, thread or links")
        for _ in missing
    ]


def _listed_in_gaps(ctx: CheckContext, number: int) -> bool:
    gaps = ctx.doc.section_text("Unverified and gaps")
    return re.search(INFERRED_LINE.format(n=number), gaps) is not None


def _has_quote(step: Step) -> bool:
    return bool(step.quotes or step.code_quotes or step.inline_code)


def _pack_skips(ctx: CheckContext, step: Step) -> bool:
    """In a shared pack, quotes with no shipped evidence are not re-verified (M5-M6 issue 1).
    Only a step that already has one tag and a quote counts; the structure rules still bite."""
    if ctx.pack is None or len(step.tags) != 1 or not _has_quote(step):
        return False
    kind = step.tags[0].kind
    return kind in ("on-screen", "written") or (kind == "spoken" and ctx.transcript is None)


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
    if tag.kind in ("spoken", "on-screen") and not _has_quote(step):
        assert tag.seconds is not None
        return [
            CheckItem(
                step=step.number,
                msg=f"[{tag.kind} {mmss(tag.seconds)}] step has no quote block",
                fix="add the exact words as a > quote or fenced block",
            )
        ]
    if _pack_skips(ctx, step):
        return []
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
    if ctx.pack is not None:
        refusal = pack_refusal(ctx.staging, ctx.work, ctx.pack)
        if refusal is not None:
            return CheckResult(
                check="provenance",
                ok=False,
                items=[
                    CheckItem(
                        msg=f"pack mode refused: {refusal}",
                        fix="check a shared pack only in the folder `skipwatch unpack` made",
                    )
                ],
            )
    failing = [item for step in ctx.doc.steps for item in _step_items(ctx, step)]
    skipped = sum(1 for step in ctx.doc.steps if _pack_skips(ctx, step))
    info = (
        [
            CheckItem(
                msg=f"shared pack: {skipped} quoted step(s) not re-verified "
                "(packs carry no frame notes or post text)"
            )
        ]
        if skipped
        else []
    )
    return CheckResult(check="provenance", ok=not failing, items=failing + info)
