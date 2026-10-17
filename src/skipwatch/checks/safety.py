"""8.7.5 safety flags. Reported with severity for the human; never edited, never a failure."""

import re
from pathlib import Path
from typing import Literal

from skipwatch.checks.redaction import MEDIA_SUFFIXES
from skipwatch.checks.runner import CheckContext, skill_files
from skipwatch.models import CheckResult, SafetyFlag

Severity = Literal["low", "medium", "high"]

_FETCH = r"(?:curl|wget|irm|iwr|Invoke-WebRequest|Invoke-RestMethod)"
_SUDO = r"(?:sudo(?:\s+-\S+)*\s+)?"
# A shell named bare, by path (/bin/bash) or through env (/usr/bin/env bash, env bash).
_SHELL = r"(?:(?:/usr)?/s?bin/|/usr/bin/env\s+|\benv\s+)?(?:ba|z|da|k|fi)?sh\b"
_INTERP = (
    r"(?:(?:/usr)?(?:/local)?/bin/|\benv\s+)?(?:python[0-9.]*|node|nodejs|perl|ruby|php|deno|bun)\b"
)
_HOME = r"(?:~|\$HOME|\$\{HOME\})"
_RC = _HOME + r"/\.(?:bashrc|bash_profile|bash_login|zshrc|zprofile|zshenv|zlogin|profile)\b"
_RM_FLAGS = r"(?:\s+-{1,2}[A-Za-z][\w-]*)*?"
_PS_FETCH = r"(?:irm|iwr|Invoke-WebRequest|Invoke-RestMethod|DownloadString)"

# Patterns run case-insensitively on logical lines (backslash continuations and trailing pipes
# joined), so `CURL ... | SH` and a pipe on the next line are caught.
SAFETY: list[tuple[str, str, Severity]] = [
    (
        "pipe_to_shell",
        rf"\b{_FETCH}\b[^\n]*\|\s*{_SUDO}{_SHELL}"
        rf"|\b{_FETCH}\b[^\n]*\|\s*xargs\b[^\n|]*\b(?:ba|z|da)?sh\b"
        rf"|(?:^|[^\w-])(?:ba|z|da|k)?sh\s+<\(\s*(?:curl|wget)\b"
        rf"|(?:^|[\s;&|(])(?:source|\.)\s+<\(\s*(?:curl|wget)\b"
        rf"|\s-c\s+[\"']?\$\(\s*(?:curl|wget)\b"
        rf"|\beval\s+[\"']?(?:\$\(|`)\s*(?:curl|wget)\b"
        rf"|\b(?:irm|iwr|Invoke-WebRequest|Invoke-RestMethod)\b[^\n]*\|\s*(?:iex|Invoke-Expression)\b"
        rf"|\b(?:iex|Invoke-Expression)\b[^\n]*\b{_PS_FETCH}\b"
        rf"|\b(?:powershell|pwsh)(?:\.exe)?\b[^\n]*\s-(?:EncodedCommand|enc|ec|e)\b"
        rf"|\bbase64\b[^\n|]*\s(?:-d|-D|--decode)\b[^\n]*\|\s*{_SUDO}{_SHELL}",
        "high",
    ),
    ("pipe_to_interpreter", rf"\b{_FETCH}\b[^\n]*\|\s*{_SUDO}{_INTERP}", "high"),
    (
        "pipe_to_variable",
        rf"\b{_FETCH}\b[^\n]*\|\s*\$\{{?\w+\}}?\s*(?:$|[;&|)])",
        "medium",
    ),
    (
        "remote_package",
        r"\bnpx\s+(?:-\S+\s+)*(?:github:|gitlab:|git\+|git@|https?://)"
        r"|\b(?:pip3?|uv\s+pip|pipx)\s+install\b[^\n]*\s(?:git\+|https?://)"
        r"|\buvx\b[^\n]*\s(?:--from\s+)?(?:git\+|https?://)",
        "medium",
    ),
    (
        "rm_rf",
        rf"\brm(?={_RM_FLAGS}\s+(?:-[A-Za-z]*[rR][A-Za-z]*|--recursive)\b)"
        rf"(?={_RM_FLAGS}\s+(?:-[A-Za-z]*f[A-Za-z]*|--force)\b)",
        "high",
    ),
    ("destructive_delete", r"\bfind\b[^\n]*\s-delete\b", "high"),
    (
        "disk_wipe",
        r"\bdd\b[^\n]*\bof=/dev/(?:r?disk\d|sd[a-z]|nvme\d|hd[a-z]|mmcblk\d|xvd[a-z])"
        r"|\bmkfs(?:\.\w+)?\b|\bwipefs\b"
        r"|\bdiskutil\s+(?:eraseDisk|eraseVolume|zeroDisk|randomDisk|secureErase|partitionDisk)\b",
        "high",
    ),
    (
        "world_writable",
        rf"\bchmod\s+(?:-\w+\s+)*(?:0?777|a\+rwx|ugo\+rwx)\s+(?:/|{_HOME})(?:/\S*)?(?=\s|$)",
        "high",
    ),
    (
        "ssh_write",
        rf"(?:>>?|\btee\s+(?:-a\s+)?|\b(?:cp|mv|install|ln|scp|rsync)\b[^\n]*\s)\s*{_HOME}/\.ssh\b",
        "high",
    ),
    (
        "shell_rc_write",
        rf"(?:>>?\s*|\btee\b(?:\s+-\w+)*\s+|\b(?:cp|mv|ln|install|rsync)\b[^\n]*\s"
        rf"|\bsed\b[^\n]*\s-i\b[^\n]*\s){_RC}",
        "high",
    ),
    (
        "persistence",
        r"\bcrontab\b(?!\s+-l\b)|\blaunchctl\s+(?:load|bootstrap|submit|enable)\b"
        r"|\bsystemctl\s+(?:--user\s+)?enable\b",
        "high",
    ),
    (
        "credential_read",
        rf"{_HOME}/\.(?:aws/credentials|aws/config|netrc|npmrc|pypirc|docker/config\.json"
        r"|kube/config|git-credentials|config/gh/hosts\.yml|gnupg\b|ssh/id_\w+)"
        r"|\bgh\s+auth\s+token\b|\bgcloud\s+auth\s+(?:application-default\s+)?print-\w+-token\b"
        r"|\baws\s+sts\s+get-session-token\b|\bop\s+(?:read|item\s+get)\b"
        r"|\bsecurity\s+(?:find-[\w-]+|dump-keychain)\b",
        "high",
    ),
    (
        "env_or_keychain_read",
        r"\b(?:cat|source|less|more|grep|head|tail)\b[^\n]*\.env\b|open\(\s*[\"'][^\"']*\.env[\"']"
        r"|\bkeychain\b",
        "high",
    ),
    (
        "network_exfil",
        r"\b(?:nc|ncat|netcat|socat)\b[^\n|]*<|\|\s*(?:nc|ncat|netcat|socat)\b",
        "high",
    ),
    (
        "upload_file",
        r"\bcurl\b[^\n]*\s(?:(?:-d|--data(?:-binary|-raw|-urlencode)?|-F|--form|--json)\s+"
        r"[\"']?[^\s\"']*@|(?:-T|--upload-file)\s)|\bwget\b[^\n]*\s--post-file\b",
        "high",
    ),
    (
        "outbound_data",
        r"\bcurl\b[^\n]*\s(?:-d|--data(?:-binary|-raw|-urlencode)?|-F|--form|--json)\b"
        r"|\bwget\b[^\n]*\s--post-data\b",
        "medium",
    ),
    (
        "disable_safety",
        r"--dangerously-skip-permissions|\bbypassPermissions\b|--yolo\b"
        r"|\b(?:skip|bypass|disable|ignore|turn\s+off|suppress)\b[^\n.]{0,40}"
        r"\b(?:confirmations?|permissions?|permission\s+prompts?|safety|safeguards?|guardrails?)\b"
        r"|\b(?:do\s+not|don't|never)\s+ask\b[^\n.]{0,40}\b(?:confirm\w*|permission)\b"
        r"|\bauto[- ]?approv\w*|\bautomatically\s+approv\w*"
        r"|\bapprove\b[^\n.]{0,40}\bautomatically\b",
        "high",
    ),
    ("hooks", r"^\s*[\"']?hooks[\"']?\s*:|[\"']hooks[\"']\s*:", "high"),
    ("allowed_tools", r"\ballowed[\s_-]?tools\b\s*[\"']?\s*[:=]", "high"),
    (
        "sudo",
        r"(?<![\w-])(?:sudo|doas)\b(?!-)|(?<![\w-])su\s+(?:-\S*\s+)*-c\b|\bpkexec\b",
        "medium",
    ),
    (
        "auto_yes",
        r"\byes\b(?:\s+\S+)?\s*\|\s*(?:sudo(?:\s+-\S+)*\s+)?"
        r"(?:\./\S+|\S*install\S*|apt(?:-get)?\b|brew\b|pip3?\b|npm\b|(?:ba|z)?sh\b|\S+\.sh\b)",
        "medium",
    ),
    (
        "write_outside_project",
        rf"(?:>>?|\btee\s+(?:-a\s+)?)\s*(?:/etc/|/usr/|/Library/|{_HOME}/)",
        "medium",
    ),
]
COMPILED: list[tuple[str, re.Pattern[str], Severity]] = [
    (kind, re.compile(pattern, re.IGNORECASE | re.MULTILINE), sev) for kind, pattern, sev in SAFETY
]
MAX_TEXT = 80
# A line already flagged as the higher-severity kind does not also get the lower one.
SUBSUMED = {
    ("outbound_data", "upload_file"),
    ("write_outside_project", "shell_rc_write"),
    ("write_outside_project", "ssh_write"),
}
CONTINUED = re.compile(r"(?:\\|\|)\s*$")


def _scanned_files(staging: Path) -> list[Path]:
    """Every regular file in the skill except images and other binaries (symlinks never)."""
    files = []
    for path in skill_files(staging):
        data = path.read_bytes()
        if path.suffix.lower() not in MEDIA_SUFFIXES and b"\x00" not in data:
            files.append(path)
    return files


def _step_at(ctx: CheckContext, line_no: int) -> int | None:
    for step in ctx.doc.steps:
        if step.start_line <= line_no < step.start_line + len(step.text.splitlines()):
            return step.number
    return None


def _clip(line: str) -> str:
    line = line.strip()
    return line if len(line) <= MAX_TEXT else line[: MAX_TEXT - 3] + "..."


def logical_lines(text: str) -> list[tuple[int, str]]:
    """(first physical line number, joined line). Joins a trailing backslash or pipe."""
    out: list[tuple[int, str]] = []
    start, parts = 0, []
    for i, line in enumerate(text.splitlines(), 1):
        if not parts:
            start = i
        cont = CONTINUED.search(line)
        if cont and line.rstrip().endswith("\\"):
            parts.append(line.rstrip()[:-1].rstrip())
        else:
            parts.append(line.strip() if parts else line)
        if not cont:
            out.append((start, " ".join(parts)))
            parts = []
    if parts:
        out.append((start, " ".join(parts)))
    return out


# `curl -o f`, `wget -O f`, `--output f`: the file a download writes ("-" is stdout, not a file).
DOWNLOAD = re.compile(
    r"\b(?:curl|wget)\b[^\n]*?\s(?:-[A-Za-z]*[oO]|--output(?:-document)?(?:=|\s))\s*"
    r"(?!-(?:\s|$))([^\s;&|]+)",
    re.IGNORECASE,
)


def _runs_file(line: str, name: str) -> bool:
    """True if the line executes `name`: sh/bash/zsh/source/. on it, or ./name after chmod."""
    f = re.escape(name.removeprefix("./"))
    start, end = r"(?:^|[\s;&|(])", r"(?:\s|$|[;&|)])"
    runner = r"(?:(?:ba|z|da)?sh|source|\.|python[0-9.]*|node)"
    run = rf"{start}{runner}\s+(?:\./)?{f}{end}"
    direct = rf"{start}\./{f}{end}"
    return re.search(run, line) is not None or re.search(direct, line) is not None


def _download_then_run(lines: list[tuple[int, str]], same_block) -> list[tuple[int, str]]:
    """(line, text) where a downloaded file is run on the same or the next logical line."""
    hits = []
    for k, (line_no, line) in enumerate(lines):
        for m in DOWNLOAD.finditer(line):
            name = m.group(1).strip("'\"")
            rest = line[m.end() :]
            nxt = lines[k + 1] if k + 1 < len(lines) else None
            later = nxt[1] if nxt and same_block(line_no, nxt[0]) else ""
            if _runs_file(rest, name) or (later and _runs_file(later, name)):
                hits.append((line_no, line))
                break
    return hits


SETTINGS_PATH = re.compile(r"(?:^|[\s'\"=/])(?:~/|\$HOME/)?\.claude/settings(?:\.local)?\.json\b")
SETTINGS_WRITE = re.compile(r">|\btee\b|\bcp\b|\bmv\b|\bsed\b[^\n]*\s-i\b|\bjq\b")
PERMISSION_KEYS = re.compile(r"permissions|\ballow\b|Bash\(\*\)|defaultMode|bypassPermissions")
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?")
RM_COMMAND = re.compile(r"\brm\b([^;&|]*)")
# A target rm -rf may delete without a high flag: relative, no wildcard, no parent, no home, no
# variable, and not the current or root folder (`rm -rf node_modules dist .next`).
SAFE_RM_TARGET = re.compile(r"^(?!\.\.?$)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9_.][A-Za-z0-9_.\-/]*$")


def _rm_severity(line: str) -> Severity:
    m = RM_COMMAND.search(line)
    targets = [t for t in (m.group(1).split() if m else []) if not t.startswith("-")]
    if targets and all(SAFE_RM_TARGET.match(t) for t in targets):
        return "medium"
    return "high"


def _settings_grants(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Writes into Claude Code settings that carry permission grants, including heredoc bodies."""
    hits = []
    for k, (line_no, line) in enumerate(lines):
        if not (SETTINGS_PATH.search(line) and SETTINGS_WRITE.search(line)):
            continue
        body = line
        heredoc = HEREDOC.search(line)
        if heredoc:
            for _, later in lines[k + 1 :]:
                if later.strip() == heredoc.group(1):
                    break
                body += "\n" + later
        if PERMISSION_KEYS.search(body):
            hits.append((line_no, line))
    return hits


def _permission_file(path: Path, text: str) -> tuple[int, str] | None:
    """A JSON or YAML file in the skill that carries permission keys: first such line."""
    if path.suffix.lower() not in (".json", ".yaml", ".yml") or path.name == "skipwatch.json":
        return None
    for line_no, line in enumerate(text.splitlines(), 1):
        if re.search(r"[\"']?(?:permissions|defaultMode|allowedTools)[\"']?\s*:", line) or (
            "bypassPermissions" in line or "Bash(*)" in line
        ):
            return line_no, line
    return None


def run(ctx: CheckContext) -> CheckResult:
    found: list[tuple[str, int, int, SafetyFlag]] = []
    seen: set[tuple[str, int, str]] = set()
    for path in _scanned_files(ctx.staging):
        text = path.read_bytes().decode("utf-8", errors="replace")
        is_skill_md = path == ctx.staging / "SKILL.md"
        lines = [(n, line) for n, line in logical_lines(text) if line.strip()]

        def same_block(a: int, b: int, is_skill_md: bool = is_skill_md) -> bool:
            return not is_skill_md or _step_at(ctx, a) == _step_at(ctx, b)

        hits: list[tuple[int, str, Severity, str]] = [
            (line_no, kind, severity, line)
            for line_no, line in lines
            for kind, pattern, severity in COMPILED
            if pattern.search(line)
        ]
        for line_no, line in _download_then_run(lines, same_block):
            hits.append((line_no, "download_then_run", "medium", line))
        for line_no, line in _settings_grants(lines):
            hits.append((line_no, "disable_safety", "high", line))
        grant_file = _permission_file(path, text)
        if grant_file:
            hits.append((grant_file[0], "disable_safety", "high", grant_file[1]))
        for line_no, kind, severity, line in hits:
            key = (path.as_posix(), line_no, kind)
            subsumed_by = [high for low, high in SUBSUMED if low == kind]
            if key in seen or any((*key[:2], high) in seen for high in subsumed_by):
                continue
            seen.add(key)
            flag = SafetyFlag(
                step=_step_at(ctx, line_no) if is_skill_md else None,
                kind=kind,
                text=_clip(line),
                severity=_rm_severity(line) if kind == "rm_rf" else severity,
            )
            found.append((path.as_posix(), line_no, len(found), flag))
    flags = [flag for *_, flag in sorted(found, key=lambda f: f[:3])]
    return CheckResult(check="safety", ok=True, flags=flags)
