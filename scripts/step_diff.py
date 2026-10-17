"""Compare the procedure steps of two SKILL.md files (M5-M6 issue 19).

Usage:
  uv run python scripts/step_diff.py <before/SKILL.md> <after/SKILL.md>

Prints one line per step whose tags, quotes or text differ (`step 2: [inferred] -> [on-screen
00:25]`), and one per added or removed step. Exits 0 when at least one step changed and 1 when
none did, so "the critic changed at least one step" is a check that can fail.
"""

import argparse
import sys
from pathlib import Path

from skipwatch.skillmd import Step, Tag, parse


def tag_text(tag: Tag) -> str:
    if tag.seconds is None:
        return f"[{tag.kind}]"
    total = int(tag.seconds)
    hours, rest = divmod(total, 3600)
    stamp = (
        f"{hours}:{rest // 60:02d}:{rest % 60:02d}"
        if hours
        else f"{rest // 60:02d}:{rest % 60:02d}"
    )
    return f"[{tag.kind} {stamp}]"


def tags_text(step: Step) -> str:
    return " ".join(tag_text(tag) for tag in step.tags) or "(no tag)"


def step_changes(before: str, after: str) -> list[str]:
    old = {step.number: step for step in parse(before).steps}
    new = {step.number: step for step in parse(after).steps}
    lines = []
    for number in sorted(old.keys() | new.keys()):
        a, b = old.get(number), new.get(number)
        if a is None:
            lines.append(f"step {number}: added")
        elif b is None:
            lines.append(f"step {number}: removed")
        elif a.tags != b.tags:
            lines.append(f"step {number}: {tags_text(a)} -> {tags_text(b)}")
        elif (a.quotes, a.code_quotes) != (b.quotes, b.code_quotes):
            lines.append(f"step {number}: quote changed")
        elif a.text != b.text:
            lines.append(f"step {number}: text changed")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args(argv)
    for path in (args.before, args.after):
        if not path.is_file():
            parser.error(f"no such file: {path}")
    lines = step_changes(
        args.before.read_text(encoding="utf-8"), args.after.read_text(encoding="utf-8")
    )
    for line in lines:
        print(line)
    return 0 if lines else 1


if __name__ == "__main__":
    sys.exit(main())
