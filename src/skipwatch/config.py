import os
import tomllib
from pathlib import Path

from pydantic import ValidationError

from skipwatch.models import Config


def skipwatch_home() -> Path:
    env = os.environ.get("SKIPWATCH_HOME")
    return Path(env).expanduser() if env else Path.home() / ".skipwatch"


def load_config(path: Path | None = None) -> Config:
    path = path or skipwatch_home() / "config.toml"
    if not path.exists():
        return Config()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"invalid config {path}: {exc}") from exc
