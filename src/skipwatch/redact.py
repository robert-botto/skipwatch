"""Secret redaction (R-CHK-2). Reports say what kind was replaced and how often, never the value.

Order: private key blocks, provider prefixes (matched on an NFKC view without invisible
characters), keys wrapped
across lines, passwords in URLs, Basic and Bearer credentials, CLI flags, named assignments,
then high entropy. Every rule leaves placeholders alone, so redaction is idempotent.
"""

import base64
import binascii
import math
import re
import unicodedata
from collections import Counter

from skipwatch.models import RedactionReplacement

PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("anthropic", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "<ANTHROPIC_API_KEY>"),
    ("openai", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}"), "<OPENAI_API_KEY>"),
    ("github", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}\b"), "<GITHUB_TOKEN>"),
    ("github", re.compile(r"github_pat_[A-Za-z0-9_]{22,}"), "<GITHUB_TOKEN>"),
    ("aws", re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "<AWS_ACCESS_KEY_ID>"),
    ("google", re.compile(r"AIza[0-9A-Za-z_\-]{35}\b"), "<GOOGLE_API_KEY>"),
    ("slack", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}\b"), "<SLACK_TOKEN>"),
    ("stripe", re.compile(r"[sr]k_(?:live|test)_[A-Za-z0-9]{16,}\b"), "<STRIPE_KEY>"),
    ("huggingface", re.compile(r"hf_[A-Za-z0-9]{30,}\b"), "<HF_TOKEN>"),
    (
        "jwt",
        re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{16,}"),
        "<JWT>",
    ),
]

PRIVATE_KEY = re.compile(
    r"-----BEGIN ([A-Z0-9 ]*)PRIVATE KEY-----.*?-----END \1PRIVATE KEY-----", re.DOTALL
)
PRIVATE_KEY_PLACEHOLDER = "<PRIVATE_KEY>"

# Zero-width space, non-joiner, joiner, BOM, soft hyphen, word joiner, Mongolian vowel separator.
INVISIBLE = "\u200b\u200c\u200d\ufeff\u00ad\u2060\u180e"

KEY_CHARS = re.compile(r"[A-Za-z0-9_\-]+")
LINE_END_TOKEN = re.compile(r"([A-Za-z0-9_\-]{6,})(\r?)$")
SPLIT_KEY_PLACEHOLDER = "(not replaced)"

URL_PASSWORD = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://[^\s:/@<>]+:)([^\s@/<>]+)(@)")
URL_PASSWORD_PLACEHOLDER = "<PASSWORD>"

BASIC = re.compile(r"(?i)\b(basic\s+)([A-Za-z0-9+/]{8,}={0,2})(?![A-Za-z0-9+/=])")
BASIC_PLACEHOLDER = "<CREDENTIALS>"
BEARER = re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9\-._~+/]{8,}=*)")
BEARER_PLACEHOLDER = "<TOKEN>"

CLI_FLAG = re.compile(
    r"(?i)(?<![\w-])(--(?:api[-_]?key|token|access[-_]?token|password|passwd|secret|"
    r"client[-_]?secret)(?:=|\s+))([\"']?)([^\s\"']+)\2"
)
MYSQL_PASSWORD = re.compile(r"\b(mysql\w*\b[^\n]*?\s-p)([^\s\"'-][^\s\"']*)")
FLAG_PLACEHOLDER = "<SECRET>"
PASSWORD_PLACEHOLDER = "<PASSWORD>"

_SECRET_NAME = r"(?:password|passwd|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key)"
ASSIGNMENT = re.compile(
    r"(?i)(?P<name>[\"']?[A-Za-z0-9_.\-]*" + _SECRET_NAME + r"[A-Za-z0-9_\-]*[\"']?)"
    r"(?P<sep>\s*[:=]\s*)"
    r"(?P<q>[\"']?)"
    r"(?P<value>[^\s\"'`,;)}\]]+)"
)
PASSWORD_NAME = re.compile(r"(?i)passw(?:or)?d")
ASSIGNMENT_PLACEHOLDER = "<SECRET>"
# Values that are code, references, placeholders or paths, not secrets.
CODE_VALUE = re.compile(r"os\.environ|process\.env|getenv|\$\{|\$\(|^\$|\(|\[|^<|ENV\[", re.I)
ATTRIBUTE = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+$")
ALL_CAPS = re.compile(r"^[A-Z][A-Z0-9_]*$")
PATH_LIKE = re.compile(r"^(?:/|~|\./|\.\./)")
MIN_SECRET_LEN = 8
MIN_PASSWORD_LEN = 6
SECRET_ENTROPY = 3.5

# high entropy: a run of 32+ [A-Za-z0-9+=_-] with Shannon entropy > 4.0 bits/char and both
# letters and digits. "/" is not in the class, so paths split into short runs. Pure hex never
# exceeds 4.0, so hashes and SHAs are kept; hex with hyphens (UUIDs) can edge past 4.0, so
# hex-and-hyphen runs are kept explicitly, as are identifiers with at most 4 digits.
HIGH_ENTROPY_RUN = re.compile(r"[A-Za-z0-9+=_\-]{32,}")
HEX_LIKE = re.compile(r"^[0-9A-Fa-f\-]+$")
IDENTIFIER_MAX_DIGITS = 4
PROTECTED = re.compile(
    r"sha(?:256|384|512)-[A-Za-z0-9+/]+={0,2}|data:[\w/+.\-]+;base64,[A-Za-z0-9+/]+={0,2}"
)
HIGH_ENTROPY_PLACEHOLDER = "<SECRET>"


def _entropy(s: str) -> float:
    counts = Counter(s)
    return -sum(n / len(s) * math.log2(n / len(s)) for n in counts.values())


def is_secret_like(run: str) -> bool:
    if HEX_LIKE.match(run):
        return False
    digits = sum(c.isdigit() for c in run)
    has_letter = any(c.isalpha() for c in run)
    if digits <= IDENTIFIER_MAX_DIGITS and not set(run) & set("+="):
        return False  # camelCase, snake_case or kebab identifiers
    return has_letter and digits > 0 and _entropy(run) > 4.0


def value_is_secret(value: str, password: bool = False) -> bool:
    """A named value worth redacting: not code, not a placeholder, and secret-shaped.

    Secret-shaped is upper, lower and digits together, or Shannon entropy of at least 3.5, at
    8+ chars. A value named as a password also counts at 6+ chars with letters and digits.
    """
    if CODE_VALUE.search(value) or ATTRIBUTE.match(value) or PATH_LIKE.match(value):
        return False
    if ALL_CAPS.match(value):
        return False
    has_digit = any(c.isdigit() for c in value)
    has_letter = any(c.isalpha() for c in value)
    if password and len(value) >= MIN_PASSWORD_LEN and has_digit and has_letter:
        return True
    if len(value) < MIN_SECRET_LEN:
        return False
    mixed = has_digit and any(c.isupper() for c in value) and any(c.islower() for c in value)
    return mixed or _entropy(value) >= SECRET_ENTROPY


def _glued_to_word(text: str, start: int) -> bool:
    """True if a prefix match continues a word: "risk-..." or "task_..." but not "KEY-" or "MY_"."""
    if start == 0:
        return False
    prev = text[start - 1]
    if prev.isalnum():
        return True
    if prev in "-_" and start >= 2:
        return text[start - 2].islower() or text[start - 2].isdigit()
    return False


def matching_view(text: str) -> tuple[str, list[int]]:
    """(view, origin): text with each character NFKC-normalised and invisible characters
    dropped, plus the index in `text` each view character came from."""
    if text.isascii():
        return text, list(range(len(text)))
    view: list[str] = []
    origin: list[int] = []
    for i, ch in enumerate(text):
        if ch in INVISIBLE:
            continue
        for out in unicodedata.normalize("NFKC", ch):
            view.append(out)
            origin.append(i)
    return "".join(view), origin


def _provider_match(token: str) -> tuple[str, str] | None:
    for kind, pattern, placeholder in PATTERNS:
        if pattern.fullmatch(token):
            return kind, placeholder
    return None


def _has_digit(s: str) -> bool:
    return any(c.isdigit() for c in s)


def _key_piece(line: str) -> bool:
    """A whole line that could continue a wrapped key: one token of key characters with a digit."""
    return bool(KEY_CHARS.fullmatch(line)) and _has_digit(line)


class _Redactor:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.placeholders: dict[str, str] = {}

    def note(self, kind: str, placeholder: str, n: int = 1) -> None:
        if n:
            self.counts[kind] = self.counts.get(kind, 0) + n
            self.placeholders[kind] = placeholder

    def private_keys(self, text: str) -> str:
        text, n = PRIVATE_KEY.subn(PRIVATE_KEY_PLACEHOLDER, text)
        self.note("private_key", PRIVATE_KEY_PLACEHOLDER, n)
        return text

    def providers(self, text: str) -> str:
        """Match keys on the NFKC view with invisible characters removed, then replace the
        original characters the match came from, so lookalike punctuation is covered too."""
        for kind, pattern, placeholder in PATTERNS:
            view, origin = matching_view(text)
            spans = [
                (origin[m.start()], origin[m.end() - 1] + 1)
                for m in pattern.finditer(view)
                if not _glued_to_word(view, m.start())
            ]
            for start, end in reversed(spans):
                text = text[:start] + placeholder + text[end:]
                self.note(kind, placeholder)
        return text

    def split_lines(self, text: str) -> str:
        """Keys wrapped onto the next line. A token that ends a line (no trailing space) joins
        a following line that is one token, only when both parts hold digits. A key spread over
        3+ lines is reported as split_key and left alone, never partly replaced."""
        lines = text.split("\n")
        i = 0
        while i < len(lines) - 1:
            m = LINE_END_TOKEN.search(lines[i])
            if not m or _glued_to_word(lines[i], m.start()):
                i += 1
                continue
            tails: list[str] = []
            j = i + 1
            while j < len(lines) and _key_piece(lines[j].strip()):
                tails.append(lines[j].strip())
                j += 1
            head = m.group(1)
            if not tails or not _has_digit(head) or not _has_digit(tails[0]):
                i += 1
                continue
            if len(tails) >= 2:
                if any(
                    _provider_match(head + "".join(tails[:k])) for k in range(1, len(tails) + 1)
                ):
                    self.note("split_key", SPLIT_KEY_PLACEHOLDER)
                i = j
                continue
            hit = _provider_match(head + tails[0])
            if hit and len(tails[0]) >= 4 and not _provider_match(head):
                self.note(*hit)
                lines[i] = lines[i][: m.start()] + hit[1] + m.group(2)
                lines[i + 1] = ""
            i = j
        return "\n".join(lines)

    def url_passwords(self, text: str) -> str:
        def fix(m: re.Match[str]) -> str:
            if m.group(2).isdigit() or m.group(2).startswith("<"):
                return m.group(0)  # host:port@..., or already a placeholder
            self.note("url_password", URL_PASSWORD_PLACEHOLDER)
            return m.group(1) + URL_PASSWORD_PLACEHOLDER + m.group(3)

        return URL_PASSWORD.sub(fix, text)

    def basic_auth(self, text: str) -> str:
        def fix(m: re.Match[str]) -> str:
            try:
                decoded = base64.b64decode(m.group(2), validate=True).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError, ValueError):
                return m.group(0)
            if ":" not in decoded:
                return m.group(0)
            self.note("basic_auth", BASIC_PLACEHOLDER)
            return m.group(1) + BASIC_PLACEHOLDER

        return BASIC.sub(fix, text)

    def bearer(self, text: str) -> str:
        def fix(m: re.Match[str]) -> str:
            if not value_is_secret(m.group(2)):
                return m.group(0)
            self.note("bearer", BEARER_PLACEHOLDER)
            return m.group(1) + BEARER_PLACEHOLDER

        return BEARER.sub(fix, text)

    def cli_flags(self, text: str) -> str:
        def flag(m: re.Match[str]) -> str:
            password = bool(PASSWORD_NAME.search(m.group(1)))
            if not value_is_secret(m.group(3), password=password):
                return m.group(0)
            self.note("cli_flag", FLAG_PLACEHOLDER)
            return m.group(1) + m.group(2) + FLAG_PLACEHOLDER + m.group(2)

        def mysql(m: re.Match[str]) -> str:
            if m.group(2).startswith("<") or len(m.group(2)) < 4:
                return m.group(0)
            self.note("mysql_password", PASSWORD_PLACEHOLDER)
            return m.group(1) + PASSWORD_PLACEHOLDER

        return MYSQL_PASSWORD.sub(mysql, CLI_FLAG.sub(flag, text))

    def assignments(self, text: str) -> str:
        def fix(m: re.Match[str]) -> str:
            password = bool(PASSWORD_NAME.search(m.group("name")))
            if not value_is_secret(m.group("value"), password=password):
                return m.group(0)
            self.note("assignment", ASSIGNMENT_PLACEHOLDER)
            return m.group("name") + m.group("sep") + m.group("q") + ASSIGNMENT_PLACEHOLDER

        return ASSIGNMENT.sub(fix, text)

    def high_entropy(self, text: str) -> str:
        protected = [m.span() for m in PROTECTED.finditer(text)]

        def fix(m: re.Match[str]) -> str:
            if any(a <= m.start() < b for a, b in protected) or not is_secret_like(m.group(0)):
                return m.group(0)
            self.note("high_entropy", HIGH_ENTROPY_PLACEHOLDER)
            return HIGH_ENTROPY_PLACEHOLDER

        return HIGH_ENTROPY_RUN.sub(fix, text)

    def report(self) -> list[RedactionReplacement]:
        return [
            RedactionReplacement(kind=k, placeholder=self.placeholders[k], count=c)
            for k, c in self.counts.items()
        ]


def redact_text(text: str) -> tuple[str, list[RedactionReplacement]]:
    """Replace secrets with placeholders. Idempotent: placeholders never match a rule.

    A `split_key` entry means a key seemed to be wrapped over 3+ lines and was not replaced;
    callers must treat it as a failure, not a redaction.
    """
    r = _Redactor()
    for step in (
        r.private_keys,
        r.providers,
        r.split_lines,
        r.url_passwords,
        r.basic_auth,
        r.bearer,
        r.cli_flags,
        r.assignments,
        r.high_entropy,
    ):
        text = step(text)
    return text, r.report()


def has_provider_key(text: str) -> bool:
    """True if a provider key pattern matches; used to scan binary files that cannot be edited."""
    return any(pattern.search(text) for _, pattern, _ in PATTERNS) or bool(PRIVATE_KEY.search(text))
