import os
import tomllib
from pathlib import Path

from pydantic import ValidationError

from skipwatch.models import Config

# `skipwatch --home <dir>`: set for one invocation by the root callback, then cleared.
_home_option: str | None = None


def set_home_option(value: str | None) -> None:
    global _home_option
    _home_option = value


def skipwatch_home() -> Path:
    """--home, else SKIPWATCH_HOME, else ~/.skipwatch; both settings resolve the same way."""
    value = _home_option or os.environ.get("SKIPWATCH_HOME")
    return Path(value).expanduser().absolute() if value else Path.home() / ".skipwatch"


def load_config(path: Path | None = None) -> Config:
    path = path or skipwatch_home() / "config.toml"
    if not path.exists():
        return Config()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"invalid config {path}: {exc}") from exc
