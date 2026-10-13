"""`skipwatch --log <file> <command>`: the engine logs and times a stage (skill audit fix 18).

While the command runs, its progress lines (sys.stderr) go to the log file; stdout, including
--json output, is untouched. When it ends, cli.main prints `rc=<n> elapsed=<s>s` and the last
three log lines on the real stderr, so the skill never builds `T0=$(date +%s); ...` by hand.
The root context closes before cli.main reports, so stop() runs first and is idempotent.
"""

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

TAIL_LINES = 3


@dataclass
class _Log:
    path: Path
    started: float
    stream: TextIO | None
    saved_stderr: TextIO


_active: _Log | None = None


def start(path: Path) -> None:
    """Send stderr to path (parents created, file overwritten) until stop()."""
    global _active
    path.parent.mkdir(parents=True, exist_ok=True)
    # never follows a symlink swapped in after cli checked the path (adversarial review REV6)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o644)
    stream = os.fdopen(fd, "w", encoding="utf-8", buffering=1)  # line-buffered, readable live
    _active = _Log(path=path, started=time.monotonic(), stream=stream, saved_stderr=sys.stderr)
    sys.stderr = stream


def stop() -> None:
    """Restore stderr and close the log. Safe to call twice."""
    if _active is None or _active.stream is None:
        return
    sys.stderr = _active.saved_stderr
    _active.stream.close()
    _active.stream = None


def active_path() -> Path | None:
    """The --log file of this run, or None without --log."""
    return _active.path if _active is not None else None


def append(text: str) -> None:
    """Add text to the --log file after stop(); a no-op without --log."""
    if _active is None:
        return
    flags = os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(_active.path, flags), "a", encoding="utf-8") as stream:
        stream.write(text if text.endswith("\n") else text + "\n")


def report(code: int) -> None:
    """Print the summary for a logged run; a no-op without --log."""
    global _active
    if _active is None:
        return
    stop()
    elapsed = round(time.monotonic() - _active.started)
    lines = _active.path.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = [line for line in lines if line.strip()][-TAIL_LINES:]
    print(f"rc={code} elapsed={elapsed}s", file=sys.stderr, flush=True)
    for line in tail:
        print(line, file=sys.stderr, flush=True)
    _active = None
