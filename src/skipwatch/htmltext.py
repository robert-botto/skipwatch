"""HTML to plain text for linked pages (R-ING-1): stdlib html.parser, no network.

Scripts, styles, navigation and footers are dropped; block elements become line breaks;
headings keep a markdown `#` prefix and list items a `- `; `pre` keeps its whitespace so code
examples survive; everything else has its whitespace collapsed.
"""

import re
from html.parser import HTMLParser

SKIP = frozenset({"script", "style", "nav", "footer", "noscript", "template", "svg", "iframe"})
BLOCK = frozenset(
    {
        "address", "article", "aside", "blockquote", "br", "dd", "details", "div", "dl", "dt",
        "figcaption", "figure", "form", "header", "hr", "main", "ol", "p", "section", "summary",
        "table", "tbody", "thead", "tr", "ul",
    }
)  # fmt: skip
HEADINGS = {f"h{n}": n for n in range(1, 7)}
# Whitespace inside <pre> is held as private-use characters until layout whitespace is tidied.
PRE_KEEP = {"\n": "\ue000", " ": "\ue001", "\t": "\ue002"}


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.skip_depth = 0
        self.pre_depth = 0
        self.in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP:
            self.skip_depth += 1
        elif tag == "title":
            self.in_title = True
        elif tag == "pre":
            self.pre_depth += 1
            self.parts.append("\n")
        elif tag in HEADINGS:
            self.parts.append("\n" + "#" * HEADINGS[tag] + " ")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in BLOCK or tag in ("td", "th"):
            self.parts.append("\n" if tag in BLOCK else " ")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP:
            self.skip_depth = max(0, self.skip_depth - 1)
        elif tag == "title":
            self.in_title = False
        elif tag == "pre":
            self.pre_depth = max(0, self.pre_depth - 1)
            self.parts.append("\n")
        elif tag in HEADINGS or tag in BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.in_title:
            self.title_parts.append(data)
        elif self.pre_depth:
            data = data.replace("\r\n", "\n")
            self.parts.append(data.translate(str.maketrans(PRE_KEEP)))
        else:
            self.parts.append(re.sub(r"\s+", " ", data))


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def html_to_text(html: str) -> tuple[str | None, str]:
    """(title, text). The title is None when the page has none."""
    parser = _Parser()
    parser.feed(html)
    parser.close()
    text = "".join(parser.parts)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip().translate(str.maketrans({v: k for k, v in PRE_KEEP.items()}))
    title = _collapse("".join(parser.title_parts)) or None
    return title, text
