import json
import re
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures"
CUE_TERMS = ("type", "run", "paste", "prompt", "copy", "settings", "click")
VTT_TIME = re.compile(r"^(\d\d):(\d\d):(\d\d)\.(\d\d\d) --> (\d\d):(\d\d):(\d\d)\.(\d\d\d)$")


def _script() -> dict:
    return json.loads((FIX / "tutorial-60s.script.json").read_text(encoding="utf-8"))


def _vtt_cues() -> list[tuple[float, float, str]]:
    """(start, end, text) for every cue in the committed VTT."""
    lines = (FIX / "tutorial-60s.en.vtt").read_text(encoding="utf-8").splitlines()
    cues = []
    for i, line in enumerate(lines):
        m = VTT_TIME.match(line)
        if m:
            g = [int(x) for x in m.groups()]
            start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
            end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
            cues.append((start, end, lines[i + 1]))
    return cues


def test_fixture_files_exist_and_are_small():
    for name in [
        "tutorial-60s.mp4",
        "tutorial-60s.en.vtt",
        "narration.wav",
        "tutorial-60s.script.json",
    ]:
        assert (FIX / name).exists(), name
    assert (FIX / "narration.wav").stat().st_size < 1_000_000
    assert (FIX / "tutorial-60s.mp4").stat().st_size < 3_000_000


def test_vtt_matches_script_timings():
    script = _script()
    vtt = (FIX / "tutorial-60s.en.vtt").read_text(encoding="utf-8")
    for s in script["sentences"]:
        assert s["text"] in vtt
    assert vtt.startswith("WEBVTT")


def test_vtt_cue_starts_equal_sentence_starts_and_do_not_overlap():
    sentences = _script()["sentences"]
    cues = _vtt_cues()
    assert [c[2] for c in cues] == [s["text"] for s in sentences]
    for (start, end, _), s in zip(cues, sentences, strict=True):
        assert abs(start - s["start"]) < 0.001
        assert end > start
    for (_, end, _), (next_start, _, _) in zip(cues, cues[1:], strict=False):
        assert end <= next_start


def test_fake_key_and_agent_text_are_present_only_as_cues():
    script = _script()
    kinds = {c["kind"] for c in script["cues"]}
    assert kinds == {"command", "prompt", "setting", "agent"}


def test_cues_are_at_spec_times_and_each_has_a_narrated_lead_in():
    """11.2 times, and a sentence with a cue term at most 1 s before each cue (R-FR-1)."""
    script = _script()
    by_kind = {c["kind"]: c for c in script["cues"]}
    assert {k: c["start"] for k, c in by_kind.items()} == {
        "command": 10.0,
        "prompt": 25.0,
        "setting": 40.0,
        "agent": 50.0,
    }
    for cue in script["cues"]:
        lead = [s for s in script["sentences"] if 0 <= cue["start"] - s["start"] <= 1.0]
        assert lead, cue
        assert any(t in lead[0]["text"].lower() for t in CUE_TERMS), lead[0]


def test_fake_key_is_obviously_fake():
    setting = next(c for c in _script()["cues"] if c["kind"] == "setting")
    assert "sk-proj-FIXTURE0NLY" in setting["text"]
