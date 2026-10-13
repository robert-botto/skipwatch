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


def marketplace_ref(root: Path) -> str:
    """The git ref the marketplace's skipwatch entry pins, or "missing" (spec issue 11)."""
    market = json.loads((root / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    for entry in market["plugins"]:
        if entry["name"] == "skipwatch":
            source = entry.get("source")
            if isinstance(source, dict) and isinstance(source.get("ref"), str):
                return source["ref"]
    return "missing"


def release_problems(root: Path, tag: str, version: str) -> list[str]:
    """What stops `tag` from being released: a tag that is not v<version>, or no changelog."""
    problems = []
    if tag != "v" + version:
        problems.append(f"MISMATCH release tag {tag}, expected v{version}")
    changelog = root / "CHANGELOG.md"
    heading = re.compile(rf"^## \[{re.escape(version)}\]", re.MULTILINE)
    if not changelog.is_file():
        problems.append("MISSING CHANGELOG.md")
    elif not heading.search(changelog.read_text(encoding="utf-8")):
        problems.append(f"MISSING CHANGELOG.md section ## [{version}]")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument(
        "--release", metavar="TAG", help="also check the tag, marketplace pin and changelog"
    )
    args = parser.parse_args()
    root = Path(args.root)
    versions = collect_versions(root)
    expected = versions["pyproject.toml"]
    for name, version in versions.items():
        print(f"{name}: {version}")
    mismatches = [(name, v) for name, v in versions.items() if v != expected]
    for name, version in mismatches:
        print(f"MISMATCH: {name} has {version}, pyproject has {expected}")
    problems = []
    if args.release is not None:
        # Main keeps an installable source; the release PR pins the tag (spec issue 11).
        ref = marketplace_ref(root)
        print(f"marketplace.json plugins[skipwatch].source.ref: {ref}")
        if ref != "v" + expected:
            problems.append(
                f"MISMATCH marketplace.json plugins[skipwatch].source.ref has {ref}, "
                f"expected v{expected}"
            )
        problems.extend(release_problems(root, args.release, expected))
    for problem in problems:
        print(problem)
    return 1 if mismatches or problems else 0


if __name__ == "__main__":
    sys.exit(main())
