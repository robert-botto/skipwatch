"""scripts/step_diff.py: the critic changed at least one procedure step (M5-M6 issue 19)."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
DRAFT = ROOT / "tests" / "fixtures" / "pipeline" / "draft" / "run-skipdemo-tutorial" / "SKILL.md"


@pytest.fixture(scope="module")
def mod() -> ModuleType:
    spec = importlib.util.spec_from_file_location("step_diff", ROOT / "scripts" / "step_diff.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_identical_files_exit_1_and_print_nothing(mod, tmp_path, capsys):
    text = DRAFT.read_text(encoding="utf-8")
    a, b = _write(tmp_path, "a.md", text), _write(tmp_path, "b.md", text)
    assert mod.main([str(a), str(b)]) == 1
    assert capsys.readouterr().out == ""


def test_retagged_step_exits_0_and_names_it(mod, tmp_path, capsys):
    text = DRAFT.read_text(encoding="utf-8")
    before = text.replace(
        "Expected: a short poem. [on-screen 00:25]", "Expected: a short poem. [inferred]"
    )
    assert before != text
    a, b = _write(tmp_path, "a.md", before), _write(tmp_path, "b.md", text)
    assert mod.main([str(a), str(b)]) == 0
    assert capsys.readouterr().out.splitlines() == ["step 2: [inferred] -> [on-screen 00:25]"]


def test_changed_text_quote_added_and_removed_steps(mod, tmp_path, capsys):
    text = DRAFT.read_text(encoding="utf-8")
    edited = text.replace("Write a four line poem about rivers", "Write a haiku about rivers")
    edited = edited.replace("1. Initialise the project.", "1. Initialise the new project.")
    added = edited.replace(
        "## Decision points",
        "5. Close the terminal.\n\n   Expected: nothing. [inferred]\n\n## Decision points",
    )
    a, b = _write(tmp_path, "a.md", text), _write(tmp_path, "b.md", added)
    assert mod.main([str(a), str(b)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out == ["step 1: text changed", "step 2: quote changed", "step 5: added"]
    assert mod.main([str(b), str(a)]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "step 5: removed"


def test_missing_file_is_usage_error(mod, tmp_path):
    with pytest.raises(SystemExit) as exc:
        mod.main([str(tmp_path / "nope.md"), str(DRAFT)])
    assert exc.value.code == 2
