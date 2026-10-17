import sys

from pydantic import BaseModel


def progress(msg: str) -> None:
    """One line of human progress on stderr (R-UX-2)."""
    print(msg.replace("\n", " "), file=sys.stderr, flush=True)


def emit_json(model: BaseModel) -> None:
    sys.stdout.write(model.model_dump_json(by_alias=True, indent=2) + "\n")
