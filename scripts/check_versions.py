"""Fail when the version drifts between pyproject, plugin manifests and skipwatch (R-ARCH-3)."""

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path


def collect_versions(root: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    versions["pyproject.toml"] = pyproject["project"]["version"]
    plugin = json.loads((root / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    versions["plugin.json"] = plugin["version"]
    market = json.loads((root / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    for entry in market["plugins"]:
        versions[f"marketplace.json plugins[{entry['name']}]"] = entry["version"]
    if not any(entry["name"] == "skipwatch" for entry in market["plugins"]):
        versions["marketplace.json plugins[skipwatch]"] = "missing"
    init = (root / "src/skipwatch/__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__ = "([^"]+)"', init)
    versions["skipwatch.__version__"] = match.group(1) if match else "missing"
    return versions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    versions = collect_versions(Path(args.root))
    expected = versions["pyproject.toml"]
    for name, version in versions.items():
        print(f"{name}: {version}")
    mismatches = [(name, v) for name, v in versions.items() if v != expected]
    for name, version in mismatches:
        print(f"MISMATCH: {name} has {version}, pyproject has {expected}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
