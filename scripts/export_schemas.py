"""Write schemas/<key>.schema.json from skipwatch.models.SCHEMA_MODELS.

--check fails on drift and on orphan schema files that no model produces; a plain run
rewrites every schema and deletes orphans.
"""

import argparse
import json
import sys
from pathlib import Path

from skipwatch.models import SCHEMA_MODELS


def render(model) -> str:
    return json.dumps(model.model_json_schema(by_alias=True), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "schemas"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stale = []
    for key, model in SCHEMA_MODELS.items():
        path = out / f"{key}.schema.json"
        text = render(model)
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(path.name)
        else:
            path.write_text(text, encoding="utf-8")
    expected = {f"{key}.schema.json" for key in SCHEMA_MODELS}
    for path in out.glob("*.schema.json"):
        if path.name in expected:
            continue
        if args.check:
            stale.append(path.name)
        else:
            path.unlink()
    if stale:
        print("stale schemas: " + ", ".join(sorted(stale)))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
