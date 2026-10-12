"""A work folder the --work guard accepts, as new-work would leave it (adversarial review REV6):
directly under the current home's work/, with a stages.json. Under the default test home that
work/ is the test's tmp_path (conftest), so home_work("w") is tmp_path / "w"."""

from pathlib import Path

from skipwatch.config import skipwatch_home
from skipwatch.workdir import WorkDir


def home_work(name: str = "w") -> Path:
    path = skipwatch_home() / "work" / name
    WorkDir(path).ensure()
    return path
