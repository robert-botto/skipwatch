"""8.7.1 frontmatter (R-SK-2, R-DIS-5, plan issue 3): portable keys only, name rules, lengths."""

import re

from skipwatch.checks.runner import CheckContext
from skipwatch.models import CheckItem, CheckResult

# The six Agent Skills keys minus allowed-tools, which R-SK-2 bans (plan issue 3).
PORTABLE_KEYS = ("name", "description", "license", "compatibility", "metadata")
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_NAME_LEN = 64
MIN_CREATOR_LEN = 3


def is_skill_name(name: str) -> bool:
    """The skill-name rule: lowercase letters, digits and single hyphens, 1 to 64 chars."""
    return 1 <= len(name) <= MAX_NAME_LEN and NAME_RE.match(name) is not None


def _short(key: object) -> str:
    """A key as shown in a report: never more than 40 chars, never a value."""
    text = str(key)
    return text if len(text) <= 40 else text[:37] + "..."


def _creator_names(ctx: CheckContext) -> list[str]:
    names = []
    for raw in (ctx.ingest.source.author, ctx.ingest.source.author_name):
        if raw:
            norm = "-".join(raw.strip().lower().lstrip("@").split())
            if len(norm) >= MIN_CREATOR_LEN:
                names.append(norm)
    return names


def _name_items(name: object, ctx: CheckContext) -> list[CheckItem]:
    if not isinstance(name, str) or not name:
        return [CheckItem(msg="name is missing", fix="add name: <verb-led-workflow-name>")]
    items = []
    if not 1 <= len(name) <= MAX_NAME_LEN:
        items.append(CheckItem(msg=f"name is {len(name)} chars; the limit is 64"))
    if not NAME_RE.match(name):
        items.append(
            CheckItem(
                msg=f"name '{name}' must be lowercase letters, digits and single hyphens",
                fix="use a lowercase, hyphenated, verb-led name",
            )
        )
    if name != ctx.staging.name:
        items.append(
            CheckItem(
                msg=f"name '{name}' does not match the folder '{ctx.staging.name}'",
                fix="rename the folder or the name so they match",
            )
        )
    for creator in _creator_names(ctx):
        if creator in name:
            items.append(
                CheckItem(
                    msg=f"name contains the creator's name '{creator}'",
                    fix="name the workflow, not the creator",
                )
            )
    return items


def run(ctx: CheckContext) -> CheckResult:
    doc = ctx.doc
    if doc.frontmatter_error is not None:
        return CheckResult(
            check="frontmatter", ok=False, items=[CheckItem(msg=doc.frontmatter_error)]
        )
    fm = doc.frontmatter
    items: list[CheckItem] = []
    if "allowed-tools" in fm:
        items.append(CheckItem(msg="allowed-tools is never allowed in generated skills"))
    for key in fm:
        if key not in PORTABLE_KEYS and key != "allowed-tools":
            items.append(
                CheckItem(
                    msg=f"key '{_short(key)}' is not portable; "
                    f"allowed keys: {', '.join(PORTABLE_KEYS)}",
                    fix=f"remove '{_short(key)}'",
                )
            )
    items += _name_items(fm.get("name"), ctx)

    description = fm.get("description")
    if not isinstance(description, str) or not 1 <= len(description) <= 1024:
        size = len(description) if isinstance(description, str) else 0
        items.append(CheckItem(msg=f"description must be 1 to 1024 chars (got {size})"))

    if "compatibility" in fm:
        compat = fm["compatibility"]
        if not isinstance(compat, str) or len(compat) >= 500:
            items.append(CheckItem(msg="compatibility must be a string under 500 chars"))

    if "metadata" in fm:
        metadata = fm["metadata"]
        if not isinstance(metadata, dict):
            items.append(CheckItem(msg="metadata must be a mapping of strings"))
        else:
            for key, value in metadata.items():
                if not isinstance(value, str):
                    items.append(
                        CheckItem(
                            msg=f"metadata.{_short(key)} must be a quoted string",
                            fix="wrap the value in double quotes",
                        )
                    )
    return CheckResult(check="frontmatter", ok=not items, items=items)
