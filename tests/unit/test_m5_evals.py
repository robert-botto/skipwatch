"""The M5 eval cases (critic-repair, pack-tamper, pack-install): layout, scaffolds, graders.

The paid runs happen from a clean export; these offline tests keep the case files honest:
every grader pattern must fail on the state it is meant to catch.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EVALS = ROOT / "evals"
FIX = ROOT / "tests" / "fixtures"
REFERENCE_SKILL = FIX / "pipeline" / "draft" / "run-skipdemo-tutorial" / "SKILL.md"
PLANTED_SKILL = FIX / "critic-work" / "staging" / "run-skipdemo-tutorial" / "SKILL.md"
ENGINE = "/Users/me/.claude/plugins/cache/skipwatch/skipwatch/0.1.0/scripts/skipwatch"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def fm(path: Path) -> dict:
    text = read(path)
    assert text.startswith("---\n"), path
    return yaml.safe_load(text.split("---\n", 2)[1])


def body(path: Path) -> str:
    return read(path).split("---\n", 2)[2].strip()


def graders(case: str) -> dict[str, dict]:
    return {p.stem: fm(p) for p in sorted((EVALS / case / "graders").glob("*.md"))}


def case_yaml(case: str) -> tuple[str, dict]:
    text = read(EVALS / case / "case.yaml")
    return text, yaml.safe_load(text)


def git_index_mode(rel: str) -> str:
    git = shutil.which("git")
    if git is None:
        pytest.skip("git not available")
    r = subprocess.run([git, "ls-files", "-s", "--", rel], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout:
        pytest.skip("not a git checkout, or the file is not committed yet")
    return r.stdout.split(" ", 1)[0]


def run_scaffold(case: str, sandbox: Path) -> None:
    if sys.platform == "win32":
        pytest.skip("running the bash scaffold is POSIX-only")
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash not available")
    sandbox.mkdir(parents=True, exist_ok=True)
    script = EVALS / case / "scaffold.sh"
    subprocess.run([bash, str(script)], cwd=sandbox, check=True)


def command_forms(command: str) -> list[str]:
    """The command as typed and as JSON tool input, where quotes become \\"."""
    return [command, json.dumps({"command": command, "description": "Run it"})]


# ---- critic-repair ----


def test_critic_repair_case_runs_alone_with_scaffold_and_tool_grant():
    text, case = case_yaml("critic-repair")
    assert "--scaffold --allow-tools Bash Write" in text and "--case critic-repair" in text
    assert case["name"] == "critic-repair"
    assert case["context"]["scaffold_script"] == "scaffold.sh"
    execution = case["execution"]
    assert execution["prompt"] == "/skipwatch resume ./.skipwatch/work/critic-demo"
    assert execution["allowed_tools"] == ["Skill", "Bash", "Read", "Write", "Agent", "Glob"]
    assert execution["max_turns"] == 120 and execution["timeout_seconds"] == 1500
    assert git_index_mode("evals/critic-repair/scaffold.sh") == "100755"


def test_critic_repair_scaffold_lays_out_a_resumable_work_folder(tmp_path):
    sandbox = tmp_path / "cwd"
    run_scaffold("critic-repair", sandbox)
    work = sandbox / ".skipwatch" / "work" / "critic-demo"
    assert (work / "logs").is_dir() and (work / "staging" / "run-skipdemo-tutorial").is_dir()
    assert read(sandbox / ".skipwatch" / ".gitignore") == "*\n"
    assert (sandbox / "tutorial-60s.mp4").is_file()
    run = json.loads(read(work / "run.json"))
    assert run["input"] == f"{sandbox}/tutorial-60s.mp4"
    assert run["flags"][run["flags"].index("--to") + 1] == f"{sandbox}/installed"
    ingest = json.loads(read(work / "ingest.json"))
    assert ingest["media"]["path"] == f"{sandbox}/tutorial-60s.mp4"
    leftover = [p.name for p in work.rglob("*.json") if "__CWD__" in read(p)]
    assert leftover == []


def test_critic_repair_graders_fail_on_the_planted_flaw_and_pass_when_repaired():
    g = graders("critic-repair")
    assert set(g) == {"critic-dispatched", "step-2-promoted", "step-2-not-a-gap", "manifest-file"}
    assert all(x.get("tool") != "Skill" for x in g.values())
    dispatched = g["critic-dispatched"]
    assert dispatched["type"] == "tool_used" and dispatched["tool"] == "Agent"
    assert dispatched["min"] == 1 and dispatched["arm"] == "with-only"
    call = {"subagent_type": "skipwatch:skill-critic", "prompt": "Critique the SkipWatch skill"}
    assert re.search(dispatched["input_match"], json.dumps(call))
    assert not re.search(dispatched["input_match"], json.dumps({"subagent_type": "frame-reader"}))

    target = "installed/run-skipdemo-tutorial/SKILL.md"
    promoted = EVALS / "critic-repair" / "graders" / "step-2-promoted.md"
    not_gap = EVALS / "critic-repair" / "graders" / "step-2-not-a-gap.md"
    assert fm(promoted)["target"] == {"source": "file", "path": target}
    assert fm(not_gap)["target"] == {"source": "file", "path": target}
    assert fm(not_gap)["match"] == "not_contains"
    planted, repaired = read(PLANTED_SKILL), read(REFERENCE_SKILL)
    assert not re.search(body(promoted), planted) and re.search(body(promoted), repaired)
    assert re.search(body(not_gap), planted) and not re.search(body(not_gap), repaired)
    assert g["manifest-file"] == {
        "type": "file_exists",
        "path": "installed/run-skipdemo-tutorial/skipwatch.json",
    }


# ---- pack-tamper ----


def test_pack_tamper_case_runs_alone_with_scaffold_and_tool_grant():
    text, case = case_yaml("pack-tamper")
    assert "--scaffold --allow-tools Bash Write" in text and "--case pack-tamper" in text
    assert case["name"] == "pack-tamper" and case["context"]["scaffold_script"] == "scaffold.sh"
    prompt = case["execution"]["prompt"]
    assert (
        prompt == "/skipwatch install run-skipdemo-tutorial-tampered.skillpack.zip --to ./installed"
    )
    assert git_index_mode("evals/pack-tamper/scaffold.sh") == "100755"


def test_pack_tamper_scaffold_copies_both_fixture_packs(tmp_path):
    sandbox = tmp_path / "cwd"
    run_scaffold("pack-tamper", sandbox)
    for name in ("run-skipdemo-tutorial", "run-skipdemo-tutorial-tampered"):
        copied = sandbox / f"{name}.skillpack.zip"
        assert copied.read_bytes() == (FIX / "packs" / f"{name}.skillpack.zip").read_bytes()


def test_pack_tamper_graders():
    g = graders("pack-tamper")
    assert set(g) == {"unpack-ran", "integrity-reported", "nothing-installed"}
    assert all(x.get("tool") != "Skill" for x in g.values())
    ran = g["unpack-ran"]
    assert ran["type"] == "tool_used" and ran["tool"] == "Bash" and ran["min"] == 1
    for form in command_forms(
        f'"{ENGINE}" unpack "/s/run-skipdemo-tutorial-tampered.skillpack.zip" --json'
    ):
        assert re.search(ran["input_match"], form), form
    for form in command_forms(f'"{ENGINE}" unpacked'):
        assert not re.search(ran["input_match"], form), form
    for form in command_forms("unzip run-skipdemo-tutorial-tampered.skillpack.zip"):
        assert not re.search(ran["input_match"], form), form
    integrity = EVALS / "pack-tamper" / "graders" / "integrity-reported.md"
    assert fm(integrity) == {"type": "regex", "target": "last_message", "match": "contains"}
    said = "Pack integrity failure: SKILL.md: hash mismatch. Nothing was installed."
    assert re.search(body(integrity), said)
    assert not re.search(body(integrity), "Installed to ./installed/run-skipdemo-tutorial.")
    assert g["nothing-installed"] == {
        "type": "file_exists",
        "path": "installed/**/SKILL.md",
        "exists": False,
    }
