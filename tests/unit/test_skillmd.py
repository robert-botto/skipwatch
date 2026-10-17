from pathlib import Path

from skipwatch.skillmd import Tag, parse, prose_spans

GOOD = (
    Path(__file__).resolve().parents[1] / "fixtures/skills/good/run-skipdemo-tutorial/SKILL.md"
).read_text(encoding="utf-8")


def test_parse_good_frontmatter():
    doc = parse(GOOD)
    assert doc.frontmatter["name"] == "run-skipdemo-tutorial"
    assert doc.frontmatter["metadata"]["extracted_at"] == "2026-10-09"
    assert doc.frontmatter_error is None
    assert doc.line_count == len(GOOD.splitlines())


def test_parse_good_sections_in_order():
    doc = parse(GOOD)
    assert [s.title for s in doc.sections if s.level == 2] == [
        "What this does",
        "Prerequisites",
        "Procedure",
        "Decision points",
        "Gotchas",
        "Verification",
        "Worked example",
        "Unverified and gaps",
        "Attribution",
    ]
    assert doc.sections[0].level == 1 and doc.sections[0].title == "Run the skipdemo tutorial"


def test_parse_good_steps_and_tags():
    doc = parse(GOOD)
    assert [s.number for s in doc.steps] == [1, 2, 3, 4]
    assert [s.tags for s in doc.steps] == [
        [Tag("on-screen", 10.0)],
        [Tag("on-screen", 25.0)],
        [Tag("on-screen", 40.0)],
        [Tag("spoken", 49.0)],
    ]


def test_parse_agent_text_under_gotchas_is_not_a_step():
    doc = parse(GOOD)
    assert all("AGENT_WAS_HERE" not in s.text for s in doc.steps)
    assert "AGENT_WAS_HERE" in doc.section_text("Gotchas")


def test_parse_step_quotes():
    doc = parse(GOOD)
    assert doc.steps[0].quotes == ["skipdemo init --name hello"]
    assert doc.steps[2].quotes == ["OPENAI_API_KEY=<OPENAI_API_KEY>"]
    assert doc.steps[3].quotes == ["Finally, click run to see the result."]


def test_parse_step_with_two_tags_and_hour_stamp():
    text = GOOD.replace("[spoken 00:49]", "[spoken 00:49] [on-screen 1:02:03]")
    tags = parse(text).steps[3].tags
    assert tags == [Tag("spoken", 49.0), Tag("on-screen", 3723.0)]


def test_parse_written_and_inferred_tags():
    text = GOOD.replace("[spoken 00:49]", "[inferred]").replace("[on-screen 00:40]", "[written]")
    doc = parse(text)
    assert doc.steps[2].tags == [Tag("written", None)]
    assert doc.steps[3].tags == [Tag("inferred", None)]


def test_parse_unquoted_date_is_not_a_string():
    doc = parse(GOOD.replace('extracted_at: "2026-10-09"', "extracted_at: 2026-10-09"))
    assert not isinstance(doc.frontmatter["metadata"]["extracted_at"], str)


def test_parse_broken_yaml_records_error():
    doc = parse(GOOD.replace("name: run-skipdemo-tutorial", "name: [unclosed"))
    assert doc.frontmatter == {} and doc.frontmatter_error


def test_parse_no_frontmatter():
    doc = parse("# Title\n\n## Procedure\n\n1. Do it. [inferred]\n")
    assert doc.frontmatter == {} and doc.frontmatter_error == "missing frontmatter"
    assert len(doc.steps) == 1


def test_prose_spans_drop_procedure_quotes_only():
    text = GOOD.replace("Sets up a tiny", "Sets up a `kept-code` tiny").replace(
        "Initialise the project.", "Initialise the `dropped-code` project."
    )
    prose = "\n".join(prose_spans(text))
    assert "Sets up a `kept-code` tiny skipdemo project" in prose
    assert "dropped-code" not in prose and "Initialise the  project." in prose
    assert "skipdemo init --name hello" not in prose
    assert "Finally, click run" not in prose
    assert "name: run-skipdemo-tutorial" not in prose


def test_parse_fenced_quote_keeps_code_indentation():
    text = GOOD.replace(
        "   ```\n   skipdemo init --name hello\n   ```",
        "   ```\n   if ready:\n       skipdemo init --name hello\n   ```",
    )
    assert parse(text).steps[0].quotes == ["if ready:\n    skipdemo init --name hello"]
