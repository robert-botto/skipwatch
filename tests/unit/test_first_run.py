"""First run: doctor reports it once per home, and the skill prints the wordmark for it."""

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch import firstrun
from skipwatch.cli import app

ROOT = Path(__file__).resolve().parents[2]
SKILL_MD = ROOT / "skills/skipwatch/SKILL.md"
BANNER_MD = ROOT / "skills/skipwatch/references/first-run-banner.md"
# the calvin_s letters of `pyfiglet -f calvin_s SKIPWATCH`
LOGO = [
    "╔═╗╦╔═╦╔═╗╦ ╦╔═╗╔╦╗╔═╗╦ ╦",
    "╚═╗╠╩╗║╠═╝║║║╠═╣ ║ ║  ╠═╣",
    "╚═╝╩ ╩╩╩  ╚╩╝╩ ╩ ╩ ╚═╝╩ ╩",
]
TAGLINE = "never send a human to watch a tutorial."  # Robert's pick; the one line to swap
# Robert's approved Matrix-rain banner, byte for byte (14 lines, half-width katakana)
BANNER = [
    "ﾁ ｦ ｽ ･ ﾃ ･   ﾌ   ｴ ｵ ﾏ ﾐ   ･       ｿ ﾜ ･   ﾑ ･ ﾑ ･   ･ ｽ ･ ﾁ     ｻ   ･",
    "ｳ ｶ ｷ ﾄ ｹ ﾎ   ﾌ   ｼ ﾐ ｵ ﾎ   ｳ       ﾔ ｳ ｸ   ｱ ﾂ ﾓ ｿ ･ ｾ ﾗ ｦ ｵ ･   ﾜ ･ ﾓ",
    "ｱ ﾍ ｯ ｽ ﾑ ﾊ ･ ｦ ･ ｲ ｿ   ﾎ   ｴ ･ ･   ﾈ ｴ ｸ ･ ﾏ ﾁ ﾔ ｱ ﾆ ﾇ ﾈ ﾆ ﾐ ﾎ ･ ｱ ﾍ ﾂ",
    "  ﾆ ﾌ ﾊ ｴ ｵ ｲ ﾑ ﾅ ｦ ｷ ･ ﾕ ･ ｾ ｼ ﾀ   ﾂ ﾔ ｼ ﾘ ﾁ ｹ ﾐ ﾄ ﾘ ﾆ ｺ ｷ ｸ ﾕ ﾎ   ｴ ﾝ",
    "  ｶ ﾟ ﾐ ｼ ﾓ ｲ                                             ﾈ   ｳ ﾜ ･ ﾘ ﾈ",
    "･ ﾈ ｳ ｿ ﾍ ﾍ ﾔ          ╔═╗╦╔═╦╔═╗╦ ╦╔═╗╔╦╗╔═╗╦ ╦          ｺ   ﾒ ｲ ﾗ ｦ ﾄ",
    "ﾈ ﾌ ｫ ｹ ﾜ ﾐ ｸ          ╚═╗╠╩╗║╠═╝║║║╠═╣ ║ ║  ╠═╣          ｺ   ﾀ ﾄ ｼ ｾ ﾍ",
    "ﾅ   ｯ ﾜ ﾋ ﾄ ﾁ          ╚═╝╩ ╩╩╩  ╚╩╝╩ ╩ ╩ ╚═╝╩ ╩          ﾈ   ｦ ﾗ ﾇ   ﾈ",
    "ｲ   ﾁ ｾ ｷ ﾌ ﾘ                                             ﾐ ･ ｱ ﾋ ｼ   ｷ",
    "ﾂ         ｶ     never send a human to watch a tutorial.   ﾋ ﾔ ﾓ ﾞ ﾐ",
    "ﾑ ･ ｴ ･   ｽ                                               ｲ ｻ   ｯ ﾝ",
    "ｽ ｷ ﾒ ｻ   ﾂ   ･ ﾋ   ｺ     ﾜ   ･ ﾊ   ｵ ﾐ ｽ ﾈ ｼ ｷ ﾁ ･   ｹ ｴ   ﾎ   ﾄ ｿ ･",
    "ﾌ ｽ ﾅ ｲ     ･ ｺ ﾑ   ｳ       ･ ﾗ     ｴ ｵ   ﾆ ﾀ   ﾅ ﾊ   ﾐ ｲ   ﾆ     ﾐ ｿ",
    "ﾔ ﾝ   ﾆ ･   ﾁ ﾊ ｻ ･ ﾝ       ﾑ ｹ     ｱ ﾗ   ﾍ ﾊ ･ ｹ ﾌ ･ ﾏ ﾐ ･ ﾁ   ﾒ ﾊ ﾝ ･",
]


def test_claim_is_true_once_per_home(tmp_path):
    home = tmp_path / ".skipwatch"
    assert firstrun.claim(home) is True
    assert firstrun.claim(home) is False
    assert (home / firstrun.MARKER).is_file()


def test_doctor_reports_first_run_once(sw_home):
    first = CliRunner().invoke(app, ["doctor", "--json"])
    assert first.exit_code == 0, first.output
    assert first.stderr.startswith("Tier ")
    assert first.stderr.splitlines()[-1] == firstrun.WELCOME
    second = CliRunner().invoke(app, ["doctor", "--json"])
    assert second.exit_code == 0, second.output
    assert firstrun.WELCOME not in second.stderr


def test_marker_symlink_is_not_followed(tmp_path):
    home = tmp_path / ".skipwatch"
    home.mkdir()
    target = tmp_path / "outside.txt"
    try:
        (home / firstrun.MARKER).symlink_to(target)
    except OSError:
        pytest.skip("symlinks need privilege here")
    assert firstrun.claim(home) is False  # a dangling link counts as present
    assert not target.exists()  # and is never followed to create its target
    target.write_text("keep", encoding="utf-8")
    assert firstrun.claim(home) is False
    assert target.read_text(encoding="utf-8") == "keep"


def test_unwritable_home_never_fails_or_repeats(tmp_path):
    home = tmp_path / ".skipwatch"
    home.write_text("a file, not a folder", encoding="utf-8")
    assert firstrun.claim(home) is False


def banner_block() -> list[str]:
    text = BANNER_MD.read_text(encoding="utf-8")
    blocks = re.findall(r"^```text\n(.*?)^```$", text, re.M | re.S)
    assert len(blocks) == 1, "one ```text block, so nothing is syntax-colored"
    return blocks[0].split("\n")[:-1]


def test_banner_file_holds_the_approved_block():
    assert banner_block() == BANNER
    assert len(BANNER) == 14 and max(len(line) for line in BANNER) <= 72
    # read once per home, so it has its own cap outside the per-run word budget
    assert len(BANNER_MD.read_text(encoding="utf-8").split()) < 400


def test_banner_hidden_columns():
    assert "".join(line[4] for line in BANNER[0:9]) == "ｽｷｯﾌﾟｳｫｯﾁ"  # SkipWatch
    assert "".join(line[64] for line in BANNER[3:12]) == "ﾎﾜｲﾄﾗﾋﾞｯﾄ"  # white rabbit


def test_banner_logo_and_tagline_lines():
    for row, letters in zip((5, 6, 7), LOGO, strict=True):  # lines 6 to 8
        assert letters in BANNER[row]
    assert TAGLINE in BANNER[9]  # line 10


def _rain(char: str) -> bool:
    """Half-width katakana (with the ･ dot) or a space: nothing a highlighter colors."""
    return char == " " or "\uff65" <= char <= "\uff9f"


def test_banner_rain_has_no_ascii_digits_or_symbols():
    for row, line in enumerate(BANNER):
        if row in (5, 6, 7):
            line = line.replace(LOGO[row - 5], " ")
        elif row == 9:
            line = line.replace(TAGLINE, " ")
        assert all(_rain(char) for char in line), (row, line)


def test_skill_reads_the_banner_only_on_a_first_run():
    text = SKILL_MD.read_text(encoding="utf-8")
    section = text.split("\n## First run\n", 1)[1].split("\n## ", 1)[0]
    assert f"`{firstrun.WELCOME}`" in section and "verbatim" in section
    assert "`references/first-run-banner.md`" in section and "```text" in section
    assert "╔═╗" not in text and "ｽ" not in text  # the banner lives in one file


def test_no_em_dash_in_first_run_sources():
    for path in (Path(firstrun.__file__), Path(__file__)):
        assert "\u2014" not in path.read_text(encoding="utf-8"), path
    assert "\u2014" not in firstrun.WELCOME


def test_banner_is_named_as_logo_art_in_both_places():
    # 2026-10-14: a real first run called the katakana rain "corrupted or garbled text"
    # and skipped it, so SKILL.md and the banner file both say what the block is
    skill = _flat(SKILL_MD.read_text(encoding="utf-8").split("\n## First run\n", 1)[1])
    first_run = skill.split(" ## ", 1)[0]
    header = _flat(BANNER_MD.read_text(encoding="utf-8").split("```text", 1)[0])
    for text in (first_run, header):
        assert "SkipWatch's logo" in text and "SKIPWATCH wordmark in katakana rain" in text
        assert "intentional, not corrupted" in text
        assert "as your very next visible text, before any further tool call" in text
        assert 'Never summarise, skip or "clean" it.' in text
    # doctor's own section says "print its report first"; the banner goes before it
    assert "before doctor's report" in first_run


def test_live_banner_check_looks_for_this_banner():
    from tests.live import test_live_first_run_banner as live

    assert live.LOGO == LOGO and live.TAGLINE == TAGLINE
    assert live.TAGLINE in BANNER[9] and all(row in BANNER[5 + i] for i, row in enumerate(LOGO))


def _flat(text: str) -> str:
    return " ".join(text.split())
