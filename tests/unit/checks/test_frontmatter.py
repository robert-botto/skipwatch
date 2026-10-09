import json

from skipwatch.checks import frontmatter
from tests.unit.checks.conftest import NAME, context_for, make_case

NAME_LINE = f"name: {NAME}"


def _run(tmp_path, edit):
    staging, work = make_case(tmp_path, edit=edit)
    return frontmatter.run(context_for(staging, work))


def _msgs(result):
    return [i.msg for i in result.items]


def test_frontmatter_fails_on_allowed_tools(tmp_path):
    r = _run(tmp_path, lambda s: s.replace(NAME_LINE, NAME_LINE + "\nallowed-tools: Bash"))
    assert not r.ok
    assert "allowed-tools is never allowed in generated skills" in _msgs(r)


def test_frontmatter_fails_on_extra_key_model(tmp_path):
    r = _run(tmp_path, lambda s: s.replace(NAME_LINE, NAME_LINE + "\nmodel: sonnet"))
    assert not r.ok and any("model" in m and "not portable" in m for m in _msgs(r))


def test_frontmatter_fails_on_uppercase_name(tmp_path):
    r = _run(tmp_path, lambda s: s.replace(NAME_LINE, "name: Run-Skipdemo-Tutorial"))
    assert not r.ok and any("lowercase" in m for m in _msgs(r))


def test_frontmatter_fails_on_name_folder_mismatch(tmp_path):
    r = _run(tmp_path, lambda s: s.replace(NAME_LINE, "name: run-other-tutorial"))
    assert not r.ok and _msgs(r) == [
        "name 'run-other-tutorial' does not match the folder 'run-skipdemo-tutorial'"
    ]


def test_frontmatter_fails_on_creator_name_in_skill_name(tmp_path):
    bad = "jane-doe-skipdemo-tutorial"
    staging, work = make_case(tmp_path, edit=lambda s: s.replace(NAME_LINE, f"name: {bad}"))
    staging = staging.rename(staging.parent / bad)
    ingest = json.loads((work / "ingest.json").read_text(encoding="utf-8"))
    ingest["source"].update(author="@JaneDoe", author_name="Jane Doe")
    (work / "ingest.json").write_text(json.dumps(ingest), encoding="utf-8")
    r = frontmatter.run(context_for(staging, work))
    assert not r.ok and _msgs(r) == ["name contains the creator's name 'jane-doe'"]


def test_frontmatter_fails_on_creator_handle_in_skill_name(tmp_path):
    bad = "janedoe-skipdemo-tutorial"
    staging, work = make_case(tmp_path, edit=lambda s: s.replace(NAME_LINE, f"name: {bad}"))
    staging = staging.rename(staging.parent / bad)
    ingest = json.loads((work / "ingest.json").read_text(encoding="utf-8"))
    ingest["source"].update(author="@JaneDoe", author_name="Jane Doe")
    (work / "ingest.json").write_text(json.dumps(ingest), encoding="utf-8")
    r = frontmatter.run(context_for(staging, work))
    assert not r.ok and _msgs(r) == ["name contains the creator's name 'janedoe'"]


def test_frontmatter_fails_on_long_description(tmp_path):
    r = _run(
        tmp_path,
        lambda s: s.replace("description: Use when", "description: " + "x" * 1020 + " Use when"),
    )
    assert not r.ok and any("description" in m and "1024" in m for m in _msgs(r))


def test_frontmatter_fails_on_long_compatibility(tmp_path):
    r = _run(
        tmp_path,
        lambda s: s.replace("compatibility: skipdemo", "compatibility: " + "y" * 500 + " skipdemo"),
    )
    assert not r.ok and any("compatibility" in m for m in _msgs(r))


def test_frontmatter_fails_on_unquoted_date_metadata(tmp_path):
    r = _run(
        tmp_path, lambda s: s.replace('extracted_at: "2026-10-09"', "extracted_at: 2026-10-09")
    )
    assert not r.ok and _msgs(r) == ["metadata.extracted_at must be a quoted string"]


def test_frontmatter_fails_on_missing_frontmatter(tmp_path):
    r = _run(tmp_path, lambda s: s.split("---\n", 2)[2])
    assert not r.ok and _msgs(r) == ["missing frontmatter"]


def test_frontmatter_fails_on_missing_description(tmp_path):
    r = _run(
        tmp_path,
        lambda s: "\n".join(line for line in s.splitlines() if not line.startswith("description:")),
    )
    assert not r.ok and any("description" in m for m in _msgs(r))


def test_frontmatter_passes(tmp_path):
    r = _run(tmp_path, None)
    assert r.ok and r.items == [] and r.check == "frontmatter"


def test_frontmatter_passes_with_license(tmp_path):
    r = _run(tmp_path, lambda s: s.replace(NAME_LINE, NAME_LINE + "\nlicense: CC-BY-4.0"))
    assert r.ok, _msgs(r)


# ---- adversarial review (m1d-review) ----

COMPAT = "compatibility:"


def _alias_bomb(depth):
    lines = ["a0: &a0 [x, x, x]"]
    for i in range(1, depth + 1):
        refs = ", ".join([f"*a{i - 1}"] * 3)
        lines.append(f"a{i}: &a{i} [{refs}]")
    return "\n".join(lines) + "\n"


def test_frontmatter_fix_never_echoes_metadata_values(tmp_path):
    r = _run(tmp_path, lambda s: s.replace('source_url: ""', "source_url: {secret_ish: 12345}"))
    assert not r.ok
    item = next(i for i in r.items if "source_url" in i.msg)
    assert "12345" not in (item.fix or "") and "12345" not in item.msg


def test_frontmatter_fails_on_yaml_alias_bomb(tmp_path):
    r = _run(tmp_path, lambda s: s.replace(COMPAT, _alias_bomb(4) + COMPAT, 1))
    assert not r.ok and _msgs(r) == [
        "frontmatter uses YAML anchors or aliases; write every value out"
    ]


def test_frontmatter_fails_on_single_anchor(tmp_path):
    r = _run(tmp_path, lambda s: s.replace(COMPAT, "x: &a 1\n" + COMPAT, 1))
    assert not r.ok and _msgs(r) == [
        "frontmatter uses YAML anchors or aliases; write every value out"
    ]


def test_frontmatter_fails_on_oversized_frontmatter(tmp_path):
    big = "license: " + "x" * (64 * 1024) + "\n"
    r = _run(tmp_path, lambda s: s.replace(COMPAT, big + COMPAT, 1))
    assert not r.ok and _msgs(r) == ["frontmatter is larger than 64 KB"]


def test_frontmatter_fails_on_duplicate_key(tmp_path):
    r = _run(tmp_path, lambda s: s.replace(COMPAT, "name: other\n" + COMPAT, 1))
    assert not r.ok and _msgs(r) == ["frontmatter has a duplicate key: name"]


def test_frontmatter_rejects_python_tags_without_running_them(tmp_path):
    marker = tmp_path / "pwned"
    tag = f"x: !!python/object/apply:os.system ['touch {marker}']\n"
    r = _run(tmp_path, lambda s: s.replace(COMPAT, tag + COMPAT, 1))
    assert not r.ok and not marker.exists()
