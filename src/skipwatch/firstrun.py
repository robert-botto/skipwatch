"""First run: true once per SkipWatch home, so the skill shows its wordmark once."""

import os
from pathlib import Path

from skipwatch.nofollow import open_nofollow

MARKER = "first-run.done"
# doctor's last stderr line on a first run; SKILL.md `## First run` keys on it verbatim
WELCOME = "Welcome to SkipWatch."


def claim(home: Path) -> bool:
    """True the first time for home, else False. The marker is created with O_CREAT | O_EXCL,
    which is atomic, through open_nofollow, so a link at the marker counts as present (on
    Windows a plain O_EXCL open would create a dangling link's target). A
    home that cannot be written returns False, so the welcome never fails a run or repeats."""
    try:
        home.mkdir(parents=True, exist_ok=True)
        fd = open_nofollow(home / MARKER, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError:
        return False
    os.close(fd)
    return True
