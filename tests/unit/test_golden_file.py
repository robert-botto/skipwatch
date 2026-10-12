"""Golden set file (spec 11.5) and the golden_check / golden_run scripts, offline."""

import importlib.util
import json
import re
import subprocess
from pathlib import Path
from types import ModuleType
from urllib.parse import parse_qs, urlparse

import pytest

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden" / "golden.json"
EXPECTED_KEYS = {
    "steps",
    "inferred_ratio_max",
    "gaps_max",
    "safety_flags_max",
    "illegible_in_quotes_max",
}
TRACKING = {"si", "feature", "utm_source", "utm_medium", "utm_campaign", "igsh", "s", "t", "pp"}


def _load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def run_mod() -> ModuleType:
    return _load_script("golden_run")


@pytest.fixture(scope="module")
def check_mod() -> ModuleType:
    return _load_script("golden_check")


# ---- golden.json shape (Task M2-F1 step 1) ----


def test_five_entries_in_order_with_platforms(golden):
    videos = golden["videos"]
    assert golden["version"] == 1
    assert [v["id"] for v in videos] == ["G1", "G2", "G3", "G4", "G5"]
    assert [v["platform"] for v in videos] == ["youtube", "x", "tiktok", "instagram", "youtube"]


def test_g1_manual_captions_and_g5_talk_length(golden):
    g1, g5 = golden["videos"][0], golden["videos"][4]
    assert g1["captions"] == "manual"
    assert 300 <= g1["duration_s"] <= 900
    assert 1500 <= g5["duration_s"] <= 2400


def test_every_expected_has_five_well_formed_keys(golden):
    for video in golden["videos"]:
        expected = video["expected"]
        assert set(expected) >= EXPECTED_KEYS, video["id"]
        low, high = expected["steps"]
        assert isinstance(low, int) and isinstance(high, int) and 0 < low <= high, video["id"]
        assert 0 <= expected["inferred_ratio_max"] <= 1, video["id"]
        assert expected["gaps_max"] >= 0, video["id"]
        assert expected["safety_flags_max"] == 0, video["id"]  # S4
        assert expected["illegible_in_quotes_max"] == 0, video["id"]  # S3


# The ranges in tests/golden/README.md and the M2-M4 plan (Task M2-F1), pinned per id.
PINNED_RANGES = {
    "G1": ([6, 30], 0.2, 1),  # raised from 20: the real G1 skill had 27 honest steps
    "G2": ([3, 15], 0.3, 2),
    "G3": ([3, 15], 0.3, 2),
    "G4": ([3, 15], 0.3, 2),
    "G5": ([8, 40], 0.3, 3),
}


def test_expected_ranges_match_the_readme(golden):
    for video in golden["videos"]:
        steps, inferred_max, gaps_max = PINNED_RANGES[video["id"]]
        expected = video["expected"]
        assert expected["steps"] == steps, video["id"]
        assert expected["inferred_ratio_max"] == inferred_max, video["id"]
        assert expected["gaps_max"] == gaps_max, video["id"]
        assert expected["safety_flags_max"] == 0, video["id"]
        assert expected["illegible_in_quotes_max"] == 0, video["id"]


def test_entries_carry_metadata_fields(golden):
    for video in golden["videos"]:
        for key in ("url", "title", "author", "why", "captions", "needs_cookies"):
            assert key in video, (video["id"], key)
        assert video["author"].startswith("@"), video["id"]
        assert video["captions"] in {"manual", "auto", "none"}, video["id"]
        assert isinstance(video["needs_cookies"], bool), video["id"]
        duration = video["duration_s"]
        assert duration is None or (isinstance(duration, int) and duration > 0), video["id"]


def test_g1_has_s2_task_and_verify_and_only_g1(golden):
    g1 = golden["videos"][0]
    assert g1["s2"]["task"].strip() and g1["s2"]["verify"].strip()
    assert all("s2" not in v for v in golden["videos"][1:])


ORDER_TS = (
    "export interface Order { id: string; items: { sku: string; qty: number }[]; "
    "customer: { name: string; email: string; address: { city: string; zip: string } }; }"
)


def test_g2_has_s3_task_verify_and_setup_and_only_g2(golden):
    s3 = golden["videos"][1]["s3"]
    assert set(s3) == {"task", "verify", "setup_files"}
    assert "DeepPartial" in s3["task"] and "orderMock" in s3["task"]
    assert s3["setup_files"] == {"models.ts": ORDER_TS + "\n"}
    verify = s3["verify"]
    assert "verify_ok.ts" in verify and "verify_bad.ts" in verify
    assert "npx --yes -p typescript@5.6 tsc --noEmit --strict --skipLibCheck" in verify
    assert "! npx" in verify  # the bad file must fail to type-check
    assert all("s3" not in v for i, v in enumerate(golden["videos"]) if i != 1)


@pytest.mark.live
def test_g2_s3_verify_passes_on_done_work_and_fails_on_undone(golden, tmp_path):
    """Live: npx fetches typescript@5.6 from npm."""
    s3 = golden["videos"][1]["s3"]
    run_mod = _load_script("golden_run")
    run_mod.write_setup_files(s3, tmp_path)
    (tmp_path / "test-utils.ts").write_text(
        "export type DeepPartial<T> = T extends (infer U)[] ? DeepPartial<U>[] : "
        "T extends object ? { [K in keyof T]?: DeepPartial<T[K]> } : T;\n"
    )
    (tmp_path / "mock.ts").write_text(
        'import type { Order } from "./models";\n'
        'import type { DeepPartial } from "./test-utils";\n'
        "export const orderMock: DeepPartial<Order> = "
        '{ customer: { address: { city: "Leeds" } }, items: [{ qty: 1 }] };\n'
    )

    def run() -> int:
        return subprocess.run(["bash", "-c", s3["verify"]], cwd=tmp_path).returncode

    assert run() == 0
    (tmp_path / "test-utils.ts").write_text("export type DeepPartial<T> = Partial<T>;\n")
    assert run() != 0  # shallow Partial: nested fields stay required


def test_g2_has_context_minimums(golden):
    context = golden["videos"][1]["expected"]["context"]
    assert set(context) == {"thread_min", "replies_min", "links_min"}
    assert all(isinstance(n, int) and n >= 0 for n in context.values())
    # Pinned to what both routes really yield (M4-A live run, 2026-10-11): the self-thread,
    # no author replies, and no links (the only t.co link is the post's own media).
    assert context == {"thread_min": 2, "replies_min": 0, "links_min": 0}


def test_urls_have_no_share_tracking_parameters(golden):
    for video in golden["videos"]:
        for url in filter(None, (video["url"], video.get("fallback_url"))):
            parsed = urlparse(url)
            assert parsed.scheme == "https", video["id"]
            assert not (set(parse_qs(parsed.query)) & TRACKING), video["id"]
            assert "?si=" not in url and "&si=" not in url, video["id"]


def test_g4_has_a_distinct_same_platform_fallback(golden):
    g4 = golden["videos"][3]
    assert g4["fallback_url"] != g4["url"]
    assert urlparse(g4["fallback_url"]).netloc == urlparse(g4["url"]).netloc


def test_golden_file_has_no_em_dash():
    assert "\u2014" not in GOLDEN.read_text(encoding="utf-8")


@pytest.mark.skipif(
    not Path("/usr/bin/jq").exists() and not Path("/opt/homebrew/bin/jq").exists(),
    reason="jq not installed",
)
def test_g1_verify_passes_on_done_work_and_fails_on_undone(golden, tmp_path):
    verify = golden["videos"][0]["s2"]["verify"]
    team = {
        "startup": "Pied Piper",
        "location": "Palo Alto",
        "team": [
            {"name": "Richard", "salary": 120000, "skills": ["compression"]},
            {"name": "Gilfoyle", "salary": 118000, "skills": ["systems"]},
            {"name": "Dinesh", "salary": 110000, "skills": ["java"]},
            {"name": "Jared", "salary": 90000, "skills": ["ops"]},
        ],
    }
    (tmp_path / "team.json").write_text(json.dumps(team))
    (tmp_path / "high_earners.txt").write_text("Richard\nGilfoyle\n")
    no_skills = [{k: v for k, v in m.items() if k != "skills"} for m in team["team"]]
    (tmp_path / "team_no_skills.json").write_text(json.dumps(no_skills))

    def run() -> int:
        return subprocess.run(["bash", "-c", verify], cwd=tmp_path).returncode

    assert run() == 0
    (tmp_path / "high_earners.txt").write_text('"Richard"\n"Gilfoyle"\n')  # not raw output
    assert run() != 0
    (tmp_path / "high_earners.txt").write_text("Richard\nGilfoyle\n")
    (tmp_path / "team_no_skills.json").write_text(json.dumps(team["team"]))  # skills kept
    assert run() != 0


# ---- golden_check.py (Task M2-F1 step 2), pure part ----


def _info(**over):
    info = {
        "duration": 612,
        "subtitles": {"en": [{}]},
        "automatic_captions": {"en": [{}]},
        "formats": [{"width": 1280, "height": 720}, {"width": 640, "height": 360}],
    }
    info.update(over)
    return info


def test_check_line_ok_for_good_youtube(check_mod):
    entry = {"id": "G1", "platform": "youtube", "captions": "manual", "needs_cookies": False}
    ok, line = check_mod.check_entry(entry, _info())
    assert ok
    assert line == "G1 OK youtube 10:12 captions=manual formats>=720p=yes"


def test_check_validates_task_entries(check_mod):
    base = {"id": "G2", "platform": "x", "captions": "none", "needs_cookies": False}
    good = {"task": "t", "verify": "true", "setup_files": {"models.ts": "x"}}
    assert check_mod.task_problems({**base, "s3": good}) == []
    assert check_mod.task_problems({**base, "s2": {"task": "t", "verify": "true"}}) == []
    assert check_mod.task_problems({**base, "s3": {"task": "", "verify": "true"}}) == [
        "s3.task is empty"
    ]
    assert check_mod.task_problems({**base, "s3": {"task": "t"}}) == ["s3.verify is empty"]
    assert check_mod.task_problems(
        {**base, "s3": {**good, "setup_files": {"../x.ts": "", "ok.ts": 3}}}
    ) == ["s3.setup_files path ../x.ts escapes the scratch dir", "s3.setup_files ok.ts not text"]
    assert check_mod.task_problems({**base, "s3": {**good, "extra": 1}}) == [
        "s3 has unknown keys: extra"
    ]


def test_check_entry_fails_on_a_bad_task(check_mod):
    entry = {
        "id": "G2",
        "platform": "x",
        "captions": "none",
        "needs_cookies": False,
        "s3": {"task": "t", "verify": ""},
    }
    ok, line = check_mod.check_entry(entry, _info(subtitles={}, automatic_captions={}))
    assert not ok and line.startswith("G2 FAIL s3.verify is empty:")


def test_check_fails_when_manual_captions_promised_but_missing(check_mod):
    entry = {"id": "G1", "platform": "youtube", "captions": "manual", "needs_cookies": False}
    ok, line = check_mod.check_entry(entry, _info(subtitles={}))
    assert not ok and line.startswith("G1 FAIL") and "captions=auto" in line


def test_check_fails_without_a_720p_format(check_mod):
    entry = {"id": "G3", "platform": "tiktok", "captions": "none", "needs_cookies": False}
    info = _info(subtitles={}, automatic_captions={}, formats=[{"width": 576, "height": 1024}])
    ok, line = check_mod.check_entry(entry, info)
    assert not ok and "formats>=720p=no" in line


def test_check_uses_short_side_for_vertical_video(check_mod):
    entry = {"id": "G4", "platform": "instagram", "captions": "none", "needs_cookies": False}
    info = _info(
        duration=None, subtitles={}, automatic_captions={}, formats=[{"width": 720, "height": 1280}]
    )
    ok, line = check_mod.check_entry(entry, info)
    assert ok, line
    assert "?:??" in line and "formats>=720p=yes" in line


def test_check_ignores_live_chat_and_non_english_tracks(check_mod):
    info = _info(subtitles={"live_chat": [{}], "de": [{}]}, automatic_captions={})
    assert check_mod.caption_kind(info) == "none"


def test_check_main_exit_code_and_only(check_mod, tmp_path, capsys):
    data = {
        "videos": [
            {
                "id": "G1",
                "url": "u1",
                "platform": "youtube",
                "captions": "manual",
                "needs_cookies": False,
            },
            {"id": "G2", "url": "u2", "platform": "x", "captions": "none", "needs_cookies": False},
        ]
    }
    path = tmp_path / "golden.json"
    path.write_text(json.dumps(data))
    seen = []

    def fetch(url):
        seen.append(url)
        if url == "u2":
            raise RuntimeError("ERROR: [twitter] gone")
        return _info()

    assert check_mod.main(["--golden", str(path), "--only", "G1"], fetch=fetch) == 0
    assert seen == ["u1"]
    assert check_mod.main(["--golden", str(path)], fetch=fetch) == 1
    out = capsys.readouterr().out
    assert "G2 FAIL ERROR: [twitter] gone" in out


# ---- golden_run.py judge (Task M2-F2) ----


def _report(steps=10, inferred=1, gaps=0, flags=0):
    return {
        "schema": "skipwatch/check/1",
        "skill": "g1-skill",
        "passed": True,
        "results": [
            {
                "check": "safety",
                "ok": flags == 0,
                "flags": [{"kind": "rm", "text": "rm -rf", "severity": "high"}] * flags,
            },
            {"check": "style", "ok": True},
        ],
        "counts": {"steps": steps, "inferred": inferred, "gaps": gaps},
    }


EXPECTED = {
    "steps": [6, 20],
    "inferred_ratio_max": 0.2,
    "gaps_max": 1,
    "safety_flags_max": 0,
    "illegible_in_quotes_max": 0,
}

SKILL_ILLEGIBLE_OUTSIDE = """---
name: g1-skill
---
# G1

1. Run the filter. [on-screen 01:02]
   Some text mentions [illegible at 01:03] in prose.

## Unverified and gaps

- [illegible at 02:00] seen once
"""

SKILL_ILLEGIBLE_IN_QUOTES = """---
name: g1-skill
---
# G1

1. Paste the prompt. [on-screen 01:02]
   > Write a [illegible at 01:03] summary
2. Run it. [on-screen 01:10]
   ```bash
   jq '.team[] | [illegible at 01:11]' team.json
   ```
"""


def test_judge_flags_illegible_inside_quotes_only(run_mod):
    assert run_mod.illegible_in_quotes(SKILL_ILLEGIBLE_OUTSIDE) == 0
    assert run_mod.illegible_in_quotes(SKILL_ILLEGIBLE_IN_QUOTES) == 2
    assert run_mod.judge(_report(), SKILL_ILLEGIBLE_OUTSIDE, EXPECTED) == []
    assert run_mod.judge(_report(), SKILL_ILLEGIBLE_IN_QUOTES, EXPECTED) == [
        "illegible_in_quotes=2 (want <=0)"
    ]


def test_judge_total_illegible_matches_the_engine_count(run_mod):
    report = _report()
    report["counts"]["illegible"] = 2  # SKILL_ILLEGIBLE_OUTSIDE has two markers
    assert run_mod.illegible_total(SKILL_ILLEGIBLE_OUTSIDE) == 2
    assert run_mod.judge(report, SKILL_ILLEGIBLE_OUTSIDE, EXPECTED) == []
    report["counts"]["illegible"] = 1  # draft and report disagree: judged the wrong file
    assert run_mod.judge(report, SKILL_ILLEGIBLE_OUTSIDE, EXPECTED) == [
        "illegible_total=2 (report counts.illegible=1)"
    ]


def test_judge_ranges(run_mod):
    assert run_mod.judge(_report(steps=6, inferred=1, gaps=1), "", EXPECTED) == []
    assert run_mod.judge(_report(steps=20), "", EXPECTED) == []
    assert run_mod.judge(_report(steps=4, inferred=0), "", EXPECTED) == ["steps=4 (want 6..20)"]
    assert run_mod.judge(_report(steps=21), "", EXPECTED) == ["steps=21 (want 6..20)"]
    assert run_mod.judge(_report(steps=10, inferred=3, gaps=2, flags=1), "", EXPECTED) == [
        "inferred=0.30 (want <=0.20)",
        "gaps=2 (want <=1)",
        "flags=1 (want <=0)",
    ]


def test_judge_ratio_at_the_ceiling_passes_and_just_above_fails(run_mod):
    assert run_mod.judge(_report(steps=10, inferred=2), "", EXPECTED) == []  # exactly 0.2
    assert run_mod.judge(_report(steps=14, inferred=3), "", EXPECTED) == [
        "inferred=0.21 (want <=0.20)"
    ]
    g2_like = {**EXPECTED, "steps": [3, 15], "inferred_ratio_max": 0.3}
    assert run_mod.judge(_report(steps=10, inferred=3), "", g2_like) == []  # exactly 0.3


G4_LIKE = {**EXPECTED, "steps": [3, 15], "inferred_ratio_max": 0.3, "gaps_max": 2}


def test_judge_tiny_skill_allows_one_inferred_step_instead_of_the_ratio(run_mod):
    # Real G4 run: 3 honest steps, the "apply" step [inferred] (1/3 = 0.33 > 0.30).
    assert run_mod.judge(_report(steps=3, inferred=1), "", G4_LIKE) == []
    assert run_mod.judge(_report(steps=5, inferred=1), "", G4_LIKE) == []
    assert run_mod.judge(_report(steps=5, inferred=2), "", G4_LIKE) == [
        "inferred=2 steps (want <=1 below 6 steps)"
    ]


def test_judge_ratio_applies_from_six_steps(run_mod):
    assert run_mod.judge(_report(steps=6, inferred=1), "", G4_LIKE) == []
    assert run_mod.judge(_report(steps=6, inferred=2), "", G4_LIKE) == [
        "inferred=0.33 (want <=0.30)"
    ]


def test_judge_zero_steps_is_out_of_range_not_a_crash(run_mod):
    assert run_mod.judge(_report(steps=0, inferred=0), "", EXPECTED) == ["steps=0 (want 6..20)"]


def test_result_line_format(run_mod):
    metrics = run_mod.metrics(_report(steps=11, inferred=1), "")
    assert run_mod.result_line("G1", metrics, [], installed=True) == (
        "G1 PASS steps=11 inferred=0.09 gaps=0 flags=0 illegible_in_quotes=0 installed=yes"
    )
    line = run_mod.result_line("G1", metrics, ["steps=4 (want 6..20)"], installed=False)
    assert line.startswith("G1 FAIL ") and line.endswith("steps=4 (want 6..20) installed=no")


# ---- golden_run.py runner with fakes ----


def _entry(**over):
    entry = {
        "id": "G4",
        "url": "https://example.test/reel/1",
        "platform": "instagram",
        "needs_cookies": True,
        "expected": EXPECTED,
    }
    entry.update(over)
    return entry


def test_claude_command_shape_and_cookie_rule(run_mod, tmp_path):
    repo = Path("/repo")
    cmd = run_mod.claude_command(_entry(), tmp_path / "out", repo, cookies=None)
    # The prompt goes right after -p: a variadic flag such as --allowedTools placed before it
    # swallows the prompt and claude exits with "Input must be provided".
    prompt = cmd[2]
    assert cmd[:2] == ["claude", "-p"]
    assert cmd[3:] == [
        "--plugin-dir",
        str(repo),
        "--allowedTools",
        "Bash,Read,Write,Agent",
    ]
    assert prompt.startswith("/skipwatch:skipwatch https://example.test/reel/1 --yes --to ")
    assert prompt.endswith(" --name g4-skill")
    assert "--cookies-from-browser" not in prompt
    with_cookies = run_mod.claude_command(_entry(), tmp_path / "out", Path("/repo"), "chrome")
    assert with_cookies[2].endswith("--cookies-from-browser chrome")
    no_need = run_mod.claude_command(_entry(needs_cookies=False), tmp_path, Path("/r"), "chrome")
    assert "--cookies-from-browser" not in no_need[2]


def test_cookies_only_from_env(run_mod):
    assert run_mod.cookies_from_env({}) is None
    assert run_mod.cookies_from_env({"SKIPWATCH_GOLDEN_COOKIES": "chrome"}) == "chrome"
    assert run_mod.cookies_from_env({"SKIPWATCH_GOLDEN_COOKIES": "firefox"}) is None


def _fake_run_writes(run_mod, out, entry, report, skill_md, install=True):
    calls = []

    def fake(cmd, *, env, timeout, **kwargs):
        calls.append((cmd, env, timeout))
        home = Path(env["SKIPWATCH_HOME"])
        work = home / "work" / "g4-20261009-120000"
        name = f"{entry['id'].lower()}-skill"
        (work / "staging" / name).mkdir(parents=True)
        (work / "staging" / name / "SKILL.md").write_text(skill_md)
        (work / "check-report.json").write_text(json.dumps(report))
        if install:
            target = out / entry["id"] / "skills" / name
            target.mkdir(parents=True)
            (target / "SKILL.md").write_text(skill_md)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    return fake, calls


def test_run_video_judges_staged_draft_in_isolated_home(run_mod, tmp_path):
    entry = _entry(needs_cookies=False)
    fake, calls = _fake_run_writes(run_mod, tmp_path, entry, _report(), SKILL_ILLEGIBLE_OUTSIDE)
    result = run_mod.run_video(entry, tmp_path, Path("/repo"), runner=fake, base_env={})
    assert result.ok and result.line.startswith("G4 PASS") and result.line.endswith("installed=yes")
    ((cmd, env, timeout),) = calls
    assert env["SKIPWATCH_HOME"] == str(tmp_path / "G4" / "home")
    assert timeout == 30 * 60


def test_run_video_fails_out_of_range_even_when_not_installed(run_mod, tmp_path):
    entry = _entry(needs_cookies=False)
    fake, _ = _fake_run_writes(
        run_mod, tmp_path, entry, _report(steps=2), SKILL_ILLEGIBLE_IN_QUOTES, install=False
    )
    result = run_mod.run_video(entry, tmp_path, Path("/repo"), runner=fake, base_env={})
    assert not result.ok
    assert (
        "steps=2 (want 6..20)" in result.line and "illegible_in_quotes=2 (want <=0)" in result.line
    )
    assert result.line.endswith("installed=no")


def test_run_video_reports_missing_draft(run_mod, tmp_path):
    def fake(cmd, *, env, timeout, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "", "boom")

    result = run_mod.run_video(_entry(), tmp_path, Path("/repo"), runner=fake, base_env={})
    assert not result.ok and result.line.startswith("G4 FAIL no check-report.json")


def test_run_video_timeout_is_a_fail_line(run_mod, tmp_path):
    def fake(cmd, *, env, timeout, **kwargs):
        raise subprocess.TimeoutExpired(cmd, timeout)

    result = run_mod.run_video(_entry(), tmp_path, Path("/repo"), runner=fake, base_env={})
    assert not result.ok and "timed out after 1800 s" in result.line


def _engine_fake(calls, fail_stage=None, write=True):
    def fake(cmd, *, env, timeout, **kwargs):
        calls.append(cmd)
        stage = cmd[1]
        if stage == fail_stage:
            return subprocess.CompletedProcess(cmd, 2, "", "warn\nunsupported source\n")
        if stage == "probe":
            probe = {"schema": "skipwatch/probe/1", "duration_s": 2183.0, "long_video": False}
            return subprocess.CompletedProcess(cmd, 0, json.dumps(probe), "")
        work = Path(cmd[cmd.index("--work") + 1])
        work.mkdir(parents=True, exist_ok=True)
        if write and stage == "transcribe":
            transcript = {"origin": "captions", "segments": [{}, {}, {}], "silent": False}
            (work / "transcript.json").write_text(json.dumps(transcript))
        if write and stage == "frames":
            (work / "frames.json").write_text(json.dumps({"frames": [{}] * 5}))
        if write and stage == "plan":
            (work / "batches.json").write_text(json.dumps({"batches": [{}]}))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    return fake


def test_engine_only_runs_the_claude_free_stages_on_the_free_provider(run_mod, tmp_path):
    calls = []
    entry = _entry(needs_cookies=False)
    result = run_mod.run_engine_only(entry, tmp_path, runner=_engine_fake(calls), base_env={})
    assert result.ok
    assert all(c[0] == run_mod.engine_binary() for c in calls)
    assert [c[1] for c in calls] == ["probe", "ingest", "transcribe", "frames", "plan"]
    assert calls[0][2:] == [entry["url"], "--json"]
    work = str(tmp_path / "G4" / "home" / "work" / "g4")
    assert calls[1][2:] == [entry["url"], "--work", work, "--provider", "free"]
    assert "--cookies-from-browser" not in sum(calls, [])
    line = result.line
    assert line.startswith("G4 ENGINE-OK probe=0/")
    for stage in ("ingest", "transcribe", "frames", "plan"):
        assert re.search(rf" {stage}=0/\d+\.\ds", line), stage
    assert line.endswith(
        "duration=2183s long_video=no origin=captions segments=3 frames=5 batches=1"
    )


def test_engine_only_stages_subset_skips_later_stages(run_mod, tmp_path):
    calls = []
    result = run_mod.run_engine_only(
        _entry(), tmp_path, runner=_engine_fake(calls), base_env={}, stages=["probe", "ingest"]
    )
    assert result.ok and [c[1] for c in calls] == ["probe", "ingest"]
    assert "transcribe=" not in result.line and "frames=" not in result.line


def test_engine_only_stops_at_first_failing_stage(run_mod, tmp_path):
    calls = []
    fake = _engine_fake(calls, fail_stage="ingest")
    result = run_mod.run_engine_only(_entry(), tmp_path, runner=fake, base_env={})
    assert not result.ok
    assert [c[1] for c in calls] == ["probe", "ingest"]
    assert result.line.startswith("G4 ENGINE-FAIL ingest exit=2 probe=0/")
    assert result.line.endswith(" ingest=2/0.0s unsupported source")


def test_engine_only_stages_can_skip_transcribe(run_mod, tmp_path):
    calls = []
    fake = _engine_fake(calls, fail_stage="transcribe")
    result = run_mod.run_engine_only(
        _entry(), tmp_path, runner=fake, base_env={}, stages=["probe", "ingest", "frames"]
    )
    assert [c[1] for c in calls] == ["probe", "ingest", "frames"]
    assert result.ok and "frames=5" in result.line


def _write_media(work: Path) -> None:
    (work / "media").mkdir(parents=True, exist_ok=True)
    (work / "media" / "video.mp4").write_bytes(b"x")
    (work / "frames").mkdir(exist_ok=True)
    (work / "frames" / "f000001.jpg").write_bytes(b"x")


def _media_left(home: Path) -> list[Path]:
    return sorted(p for p in home.glob("work/*/*") if p.name in {"media", "frames"})


@pytest.mark.parametrize("keep", [False, True])
def test_run_video_deletes_media_and_frames_unless_kept(run_mod, tmp_path, keep):
    entry = _entry(needs_cookies=False)
    fake, _ = _fake_run_writes(run_mod, tmp_path, entry, _report(), SKILL_ILLEGIBLE_OUTSIDE)

    def fake_with_media(cmd, *, env, timeout, **kwargs):
        result = fake(cmd, env=env, timeout=timeout, **kwargs)
        _write_media(Path(env["SKIPWATCH_HOME"]) / "work" / "g4-20261009-120000")
        return result

    result = run_mod.run_video(
        entry, tmp_path, Path("/repo"), runner=fake_with_media, base_env={}, keep_media=keep
    )
    home = tmp_path / "G4" / "home"
    assert result.ok  # judged before the cleanup
    assert (len(_media_left(home)) == 2) is keep
    assert list(home.glob("work/*/check-report.json"))  # judging inputs stay


def test_run_video_cleans_up_after_a_failed_run_too(run_mod, tmp_path):
    def fake(cmd, *, env, timeout, **kwargs):
        _write_media(Path(env["SKIPWATCH_HOME"]) / "work" / "g4-x")
        return subprocess.CompletedProcess(cmd, 1, "", "boom")

    result = run_mod.run_video(_entry(), tmp_path, Path("/repo"), runner=fake, base_env={})
    assert not result.ok and _media_left(tmp_path / "G4" / "home") == []


@pytest.mark.parametrize("fail_stage", [None, "plan"])
@pytest.mark.parametrize("keep", [False, True])
def test_engine_only_deletes_media_and_frames_unless_kept(run_mod, tmp_path, keep, fail_stage):
    calls = []
    inner = _engine_fake(calls, fail_stage=fail_stage)

    def fake(cmd, *, env, timeout, **kwargs):
        if cmd[1] == "ingest":
            _write_media(Path(cmd[cmd.index("--work") + 1]))
        return inner(cmd, env=env, timeout=timeout, **kwargs)

    result = run_mod.run_engine_only(_entry(), tmp_path, runner=fake, base_env={}, keep_media=keep)
    assert result.ok is (fail_stage is None)
    if fail_stage is None:
        assert "frames=5" in result.line  # counts read before the cleanup
    assert (len(_media_left(tmp_path / "G4" / "home")) == 2) is keep


def test_write_setup_files_writes_each_file_and_refuses_escapes(run_mod, tmp_path):
    spec = {"task": "t", "verify": "true", "setup_files": {"models.ts": "x\n", "a/b.ts": "y"}}
    run_mod.write_setup_files(spec, tmp_path)
    assert (tmp_path / "models.ts").read_text() == "x\n"
    assert (tmp_path / "a" / "b.ts").read_text() == "y"
    run_mod.write_setup_files({"task": "t", "verify": "true"}, tmp_path)  # none: no-op
    for bad in ("../x.ts", "/etc/x.ts"):
        with pytest.raises(ValueError):
            run_mod.write_setup_files({"setup_files": {bad: ""}}, tmp_path / "s")


def test_main_prepare_writes_setup_and_prints_task(run_mod, tmp_path, capsys):
    golden = {
        "videos": [
            _entry(id="G1", s2={"task": "do one", "verify": "true"}),
            _entry(id="G2", s3={"task": "do two", "verify": "true", "setup_files": {"m.ts": "z"}}),
        ]
    }
    path = tmp_path / "golden.json"
    path.write_text(json.dumps(golden))
    scratch = tmp_path / "scratch"
    assert run_mod.main(["--golden", str(path), "--prepare", "G2", "--dir", str(scratch)]) == 0
    assert (scratch / "m.ts").read_text() == "z"
    assert capsys.readouterr().out == "do two\n"
    assert run_mod.main(["--golden", str(path), "--prepare", "G1", "--dir", str(scratch)]) == 0
    assert capsys.readouterr().out == "do one\n"
    with pytest.raises(SystemExit):
        run_mod.main(["--golden", str(path), "--prepare", "G2"])  # --dir is required


def test_main_only_selection_and_exit(run_mod, tmp_path, capsys, monkeypatch):
    golden = {"videos": [_entry(id="G1", needs_cookies=False), _entry(id="G2")]}
    path = tmp_path / "golden.json"
    path.write_text(json.dumps(golden))
    seen = []

    def fake_run_video(entry, out, plugin_dir, runner, base_env, keep_media):
        seen.append(entry["id"])
        return run_mod.VideoResult(entry["id"], entry["id"] == "G1", f"{entry['id']} X")

    monkeypatch.setattr(run_mod, "run_video", fake_run_video)
    args = ["--golden", str(path), "--out", str(tmp_path / "o")]
    assert run_mod.main([*args, "--only", "G1"]) == 0
    assert seen == ["G1"]
    assert run_mod.main(args) == 1
    with pytest.raises(SystemExit):
        run_mod.main([*args, "--only", "G9"])
