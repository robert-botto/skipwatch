"""Parse a generated SKILL.md into frontmatter, sections and procedure steps."""

import html
import re
from dataclasses import dataclass, field
from typing import Any, Literal

import yaml

TagKind = Literal["spoken", "on-screen", "written", "inferred"]

TAG = re.compile(
    r"\[(spoken|on-screen) (\d{1,2}):(\d{2})(?::(\d{2}))?\]|\[(written)\]|\[(inferred)\]"
)
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
STEP = re.compile(r"^(\d+)\.\s")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
INLINE_CODE = re.compile(r"`[^`\n]*`")
INLINE_CODE_BODY = re.compile(r"`([^`\n]+)`")
PRE = re.compile(r"<pre[^>]*>(.*?)</pre>", re.DOTALL | re.IGNORECASE)
MAX_FRONTMATTER_BYTES = 64 * 1024


@dataclass(frozen=True)
class Tag:
    kind: TagKind
    seconds: float | None


@dataclass
class Section:
    title: str
    level: int
    start_line: int


@dataclass
class Step:
    number: int
    text: str
    tags: list[Tag]
    quotes: list[str]
    start_line: int
    code_quotes: list[str] = field(default_factory=list)


@dataclass
class SkillDoc:
    frontmatter: dict[str, Any]
    frontmatter_raw: str
    body: str
    sections: list[Section]
    steps: list[Step]
    line_count: int
    frontmatter_error: str | None = None
    body_start_line: int = 1
    body_lines: list[str] = field(default_factory=list)

    def section_text(self, title: str) -> str:
        """Body text of the first H2 section with this title, up to the next H1 or H2."""
        for i, sec in enumerate(self.sections):
            if sec.level == 2 and sec.title == title:
                end = next(
                    (s.start_line for s in self.sections[i + 1 :] if s.level <= 2),
                    self.line_count + 1,
                )
                first = sec.start_line - self.body_start_line + 1
                last = end - self.body_start_line
                return "\n".join(self.body_lines[first:last])
        return ""


def _split_frontmatter(text: str) -> tuple[str, str, int, str | None]:
    """(raw frontmatter, body, 1-based line where body starts, error)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return "", text, 1, "missing frontmatter"
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1 :]), i + 2, None
    return "", text, 1, "frontmatter is not closed with ---"


class _DuplicateKey(yaml.YAMLError):
    pass


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate mapping keys instead of keeping the last one."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)  # pyright: ignore[reportArgumentType]
            if key in seen:
                raise _DuplicateKey(f"frontmatter has a duplicate key: {str(key)[:40]}")
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _uses_anchors(raw: str) -> bool:
    """Scan parser events only (no construction), so an alias bomb is never expanded."""
    for event in yaml.parse(raw, Loader=yaml.SafeLoader):
        if isinstance(event, yaml.AliasEvent) or getattr(event, "anchor", None):
            return True
    return False


def _load_frontmatter(raw: str) -> tuple[dict[str, Any], str | None]:
    if len(raw.encode("utf-8")) > MAX_FRONTMATTER_BYTES:
        return {}, "frontmatter is larger than 64 KB"
    if not raw.strip():
        return {}, "frontmatter is not a mapping"
    try:
        if _uses_anchors(raw):
            return {}, "frontmatter uses YAML anchors or aliases; write every value out"
        loaded = yaml.load(raw, Loader=_StrictLoader)
    except _DuplicateKey as exc:
        return {}, str(exc)
    except yaml.YAMLError as exc:
        return {}, f"frontmatter is not valid YAML: {str(exc).splitlines()[0][:120]}"
    if not isinstance(loaded, dict):
        return {}, "frontmatter is not a mapping"
    return loaded, None


def tags_in(text: str) -> list[Tag]:
    tags: list[Tag] = []
    for m in TAG.finditer(text):
        if m.group(1):
            a, b, c = int(m.group(2)), int(m.group(3)), m.group(4)
            seconds = a * 3600 + b * 60 + int(c) if c is not None else a * 60 + b
            tags.append(Tag(m.group(1), float(seconds)))  # pyright: ignore[reportArgumentType]
        else:
            tags.append(Tag(m.group(5) or m.group(6), None))  # pyright: ignore[reportArgumentType]
    return tags


def fence_spans(lines: list[str]) -> list[tuple[int, int]]:
    """(open, close) line indexes of closed fences. CommonMark rule: the closing fence uses the
    same character, at least as many of it, and nothing else. An unclosed fence is prose."""
    spans: list[tuple[int, int]] = []
    opened: tuple[int, str, int] | None = None
    for i, line in enumerate(lines):
        m = FENCE.match(line)
        if not m:
            continue
        marker = m.group(1)
        if opened is None:
            opened = (i, marker[0], len(marker))
        elif marker[0] == opened[1] and len(marker) >= opened[2] and not line[m.end() :].strip():
            spans.append((opened[0], i))
            opened = None
    return spans


def _step_parts(lines: list[str], marker_width: int) -> tuple[list[str], list[str], list[str]]:
    """(lines outside quotes, quotes, code quotes).

    A quote is one fenced block or one `>` run. Code quotes are what a step shows as code without
    a fence: indented code blocks, <pre> blocks and inline code in the action paragraph.
    """
    outside: list[str] = []
    quotes: list[str] = []
    code_quotes: list[str] = []
    spans = fence_spans(lines)
    opens = {a: b for a, b in spans}
    inside = {i for a, b in spans for i in range(a, b + 1)}
    quote_run: list[str] = []
    code_run: list[str] = []

    def end_runs() -> None:
        if quote_run:
            quotes.append(" ".join(quote_run))
            quote_run.clear()
        if code_run:
            code_quotes.append("\n".join(code_run))
            code_run.clear()

    for i, line in enumerate(lines):
        if i in opens:
            end_runs()
            indent = len(line) - len(line.lstrip())
            body = []
            for inner in lines[i + 1 : opens[i]]:
                # Drop the list indentation the fence carries, keep the code's own indentation.
                pad = min(indent, len(inner) - len(inner.lstrip()))
                body.append(inner[pad:].rstrip())
            quotes.append("\n".join(body).strip("\n"))
            continue
        if i in inside:
            continue
        stripped = line.lstrip()
        if stripped.startswith(">"):
            quote_run.append(stripped[1:].strip())
            continue
        if i > 0 and stripped and len(line) - len(stripped) >= marker_width + 4:
            code_run.append(line[marker_width + 4 :].rstrip())
            continue
        end_runs()
        outside.append(line)
    end_runs()
    text = "\n".join(outside)
    for m in PRE.finditer(text):
        code_quotes.append(html.unescape(m.group(1)).strip())
    outside = PRE.sub("", text).split("\n")
    action = "\n".join(outside).split("\n\n", 1)[0]
    code_quotes += INLINE_CODE_BODY.findall(TAG.sub("", action))
    return outside, quotes, code_quotes


def parse(text: str) -> SkillDoc:
    raw, body, body_start, error = _split_frontmatter(text)
    frontmatter: dict[str, Any] = {}
    if error is None:
        frontmatter, error = _load_frontmatter(raw)
    body_lines = body.splitlines()

    sections: list[Section] = []
    fenced = fenced_lines(body_lines)
    for i, line in enumerate(body_lines):
        m = HEADING.match(line)
        if m and i not in fenced:
            sections.append(Section(m.group(2), len(m.group(1)), body_start + i))

    doc = SkillDoc(
        frontmatter=frontmatter,
        frontmatter_raw=raw,
        body=body,
        sections=sections,
        steps=[],
        line_count=len(text.splitlines()),
        frontmatter_error=error,
        body_start_line=body_start,
        body_lines=body_lines,
    )
    doc.steps = _steps(doc)
    return doc


def _steps(doc: SkillDoc) -> list[Step]:
    procedure = doc.section_text("Procedure")
    if not procedure:
        return []
    proc_sec = next(s for s in doc.sections if s.level == 2 and s.title == "Procedure")
    starts: list[tuple[int, int]] = []
    lines = procedure.splitlines()
    fenced = fenced_lines(lines)
    for i, line in enumerate(lines):
        m = STEP.match(line)
        if m and i not in fenced:
            starts.append((i, int(m.group(1))))
    steps: list[Step] = []
    for k, (i, number) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        chunk = lines[i:end]
        marker = STEP.match(chunk[0])
        outside, quotes, code_quotes = _step_parts(chunk, len(marker.group(0)) if marker else 3)
        steps.append(
            Step(
                number=number,
                text="\n".join(chunk).strip(),
                tags=tags_in(INLINE_CODE.sub("", "\n".join(outside))),
                quotes=quotes,
                start_line=proc_sec.start_line + 1 + i,
                code_quotes=code_quotes,
            )
        )
    return steps


def fenced_lines(lines: list[str]) -> set[int]:
    """Indexes of lines inside closed fences, markers included. An unclosed fence is prose."""
    return {i for a, b in fence_spans(lines) for i in range(a, b + 1)}


def _quoting_step_lines(doc: SkillDoc) -> set[int]:
    """Body line indexes of Procedure steps whose quotes are source text (not [inferred])."""
    lines: set[int] = set()
    for step in doc.steps:
        if any(tag.kind == "inferred" for tag in step.tags):
            continue
        first = step.start_line - doc.body_start_line
        lines.update(range(first, first + len(step.text.splitlines())))
    return lines


def prose_spans(text: str, quotes_exempt: Literal["procedure", "all"] = "procedure") -> list[str]:
    """Body lines that are generated prose.

    Fenced blocks, blockquotes and inline code are verbatim quotes and exempt, but in SKILL.md
    (`quotes_exempt="procedure"`) only inside Procedure steps that quote a source: not before
    step 1 and not in [inferred] steps. Reference files (`"all"`) are evidence, so their quotes
    are exempt everywhere.
    """
    _, body, _, _ = _split_frontmatter(text)
    lines = body.splitlines()
    fenced = fenced_lines(lines)
    quoting = _quoting_step_lines(parse(text)) if quotes_exempt == "procedure" else set()
    spans: list[str] = []
    for i, line in enumerate(lines):
        exempt_here = quotes_exempt == "all" or i in quoting
        if exempt_here and (i in fenced or line.lstrip().startswith(">")):
            continue
        if i in fenced and FENCE.match(line):
            continue
        prose = INLINE_CODE.sub("", line) if exempt_here else line
        if prose.strip():
            spans.append(prose)
    return spans
