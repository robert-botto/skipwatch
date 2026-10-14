"""README, demo GIF and repo graphics (plan Task M6-B1)."""

import importlib.util
import io
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from types import ModuleType

import pytest
import typer
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from skipwatch.cli import app
from skipwatch.errors import ExitCode

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "docs/demo"
ASSETS = ROOT / "docs/assets"
EM_DASH = chr(0x2014)
README = ROOT / "README.md"


def _script(name: str) -> ModuleType:
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_run_is_a_cleaned_real_log():
    lines = (DEMO / "demo-run.txt").read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("> /skipwatch https://x.com/")
    assert "Skill ready for review: g2-skill" in lines
    text = "\n".join(lines)
    for scratch in ("/private/", "/tmp/", "/Users/", "/home/"):
        assert scratch not in text, scratch


def test_demo_gif_is_a_small_looping_960x540_animation():
    path = DEMO / "demo.gif"
    assert path.stat().st_size < 3 * 1024 * 1024
    with Image.open(path) as gif:
        assert gif.format == "GIF"
        assert gif.size == (960, 540)
        assert gif.info.get("loop") == 0
        assert gif.n_frames > 20
        total_ms = 0
        for index in range(gif.n_frames):
            gif.seek(index)
            total_ms += gif.info["duration"]
    assert 15_000 <= total_ms <= 25_000


def test_make_demo_gif_is_deterministic():
    make = _script("make_demo_gif")
    lines = ["> /skipwatch demo.mp4", "", "Skill ready for review: demo", "  Steps: 1"]
    first, second = io.BytesIO(), io.BytesIO()
    make.render(lines, first)
    make.render(lines, second)
    assert first.getvalue() == second.getvalue()
    assert first.getvalue()[:6] == b"GIF89a"


def _svg(name: str) -> str:
    text = (ASSETS / name).read_text(encoding="utf-8")
    ET.fromstring(text)  # well-formed
    lowered = text.lower()
    assert "<image" not in lowered and "@import" not in lowered and "@font-face" not in lowered
    assert 'href="http' not in lowered.replace('xmlns="http', "")
    return text


def _without_style(svg: str) -> str:
    start, end = svg.index("<style>"), svg.index("</style>")
    return svg[:start] + svg[end:]


def test_hero_svgs_share_one_drawing_and_differ_only_in_colours():
    light, dark = _svg("hero.svg"), _svg("hero-dark.svg")
    assert "Paste a video. Claude knows kung fu." in light
    assert _without_style(light) == _without_style(dark)
    assert light != dark


def test_how_it_works_uses_the_real_stage_names():
    light, dark = _svg("how-it-works.svg"), _svg("how-it-works-dark.svg")
    assert _without_style(light) == _without_style(dark)
    for stage in ("ingest", "transcribe", "frames", "read", "critique", "check", "review"):
        assert f">{stage}<" in light, stage
    for check in ("provenance", "redaction", "safety"):
        assert check in light, check
    assert "frame-reader" in light and "skill-critic" in light


def test_social_preview_is_a_1280x640_png_under_1_mb():
    path = ASSETS / "social-preview.png"
    assert path.stat().st_size < 1024 * 1024
    with Image.open(path) as card:
        assert card.format == "PNG" and card.size == (1280, 640)


def _rain_font_or_skip(make: ModuleType) -> Path:
    font = make.find_rain_font()
    if font is None:
        pytest.skip("no font with half-width katakana on this machine")
    return font


def test_social_preview_is_deterministic():
    make = _script("make_social_preview")
    font = _rain_font_or_skip(make)
    first, second = io.BytesIO(), io.BytesIO()
    make.render(first, font)
    make.render(second, font)
    assert first.getvalue() == second.getvalue()


def _rain_problems(make: ModuleType, font: Path) -> dict[str, bool]:
    """Where the rain landed: on drawn pixels, within 10 px of them, or inside the clear ellipse."""
    plain = make.render_plain()
    rained = make.add_rain(plain, font)
    size = plain.size
    drawn = ImageChops.difference(plain, Image.new("RGB", size, make.BG)).convert("L")
    drawn = drawn.point(lambda v: 255 if v else 0)
    rain = ImageChops.difference(plain, rained).convert("L").point(lambda v: 255 if v else 0)
    inside = Image.new("L", size, 0)
    ImageDraw.Draw(inside).rectangle((36, 36, size[0] - 36, size[1] - 36), fill=255)
    near = ImageChops.multiply(drawn, inside).filter(ImageFilter.MaxFilter(21))
    center = Image.new("L", size, 0)
    ax, ay = 0.31 * size[0], 0.26 * size[1]
    cx, cy = size[0] / 2, size[1] / 2
    ImageDraw.Draw(center).ellipse((cx - ax, cy - ay, cx + ax, cy + ay), fill=255)
    return {
        "rain": rain.getbbox() is not None,
        "on_drawn": ImageChops.multiply(rain, drawn).getbbox() is not None,
        "near_text": ImageChops.multiply(rain, near).getbbox() is not None,
        "in_center": ImageChops.multiply(rain, center).getbbox() is not None,
    }


def test_social_preview_rain_stays_off_the_text():
    make = _script("make_social_preview")
    font = _rain_font_or_skip(make)
    assert _rain_problems(make, font) == {
        "rain": True,
        "on_drawn": False,
        "near_text": False,
        "in_center": False,
    }


def test_social_preview_rain_check_catches_a_missing_vignette(monkeypatch: pytest.MonkeyPatch):
    make = _script("make_social_preview")
    font = _rain_font_or_skip(make)
    monkeypatch.setattr(make, "_vignette", lambda: Image.new("L", (make.WIDTH, make.HEIGHT), 255))
    assert _rain_problems(make, font)["in_center"]


def test_social_preview_rain_check_catches_a_missing_halo(monkeypatch: pytest.MonkeyPatch):
    make = _script("make_social_preview")
    font = _rain_font_or_skip(make)
    monkeypatch.setattr(make, "_clearance", lambda drawn: Image.new("L", drawn.size, 255))
    assert _rain_problems(make, font)["near_text"]


def test_social_preview_refuses_to_render_without_a_katakana_font(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    make = _script("make_social_preview")
    not_a_font = tmp_path / "not-a-font.ttf"
    not_a_font.write_bytes(b"not a font")
    out = tmp_path / "card.png"
    argv = ["make_social_preview.py", "-o", str(out), "--rain-font", str(not_a_font)]
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit) as exited:
        make.main()
    assert exited.value.code not in (0, None)
    assert "half-width katakana" in capsys.readouterr().err
    assert not out.exists()


# README (plan Task M6-B1)


def _readme() -> str:
    return README.read_text(encoding="utf-8")


FENCE = re.compile(r"^(`{3,})[^\n]*\n(.*?)^\1", flags=re.M | re.S)


def _code(markdown: str) -> list[str]:
    """Every inline code span and every line of every fenced block."""
    lines = [line for _, block in FENCE.findall(markdown) for line in block.splitlines()]
    return lines + re.findall(r"`([^`\n]+)`", FENCE.sub("", markdown))


def _skill_md_flags() -> set[str]:
    text = (ROOT / "skills/skipwatch/SKILL.md").read_text(encoding="utf-8")
    return set(re.findall(r"^\| `(--[a-z-]+)", text, flags=re.M))


SLASH_WORDS = {"doctor", "resume", "list", "pack", "install", "share"}  # SKILL.md first tokens


def test_readme_has_tagline_and_install_lines():
    text = _readme()
    assert "Paste a video. Claude knows kung fu." in text
    for line in (
        "/plugin marketplace add robert-botto/skipwatch",
        "/plugin install skipwatch@skipwatch",
        "claude plugin install skipwatch --marketplace robert-botto/skipwatch",
        "claude plugin marketplace add robert-botto/skipwatch#v0.1.0",
    ):
        assert line in text, line


def test_readme_relative_links_and_images_resolve():
    text = FENCE.sub("", _readme())  # links inside code samples are not links
    targets = re.findall(r"\]\(([^)\s]+)\)", text)
    targets += re.findall(r'(?:src|srcset|href)="([^"]+)"', text)
    relative = [t for t in targets if not re.match(r"[a-z]+:|#", t)]
    assert relative, "the README links no local files"
    for target in relative:
        assert (ROOT / target.split("#")[0]).exists(), target


def test_readme_skipwatch_commands_and_their_flags_exist():
    group = typer.main.get_command(app)
    commands = group.commands  # type: ignore[attr-defined]
    seen = 0
    for code in _code(_readme()):
        for match in re.finditer(r"(?:^|[\s(])skipwatch ([a-z][a-z-]*)([^`]*)", code):
            name, rest = match.groups()
            assert name in commands, f"skipwatch {name}"
            options = {opt for param in commands[name].params for opt in param.opts}
            for flag in re.findall(r"(?<![\w-])(--?[a-z][a-z-]*)", rest):
                assert flag in options, f"skipwatch {name} {flag}"
            seen += 1
    assert seen >= 5


def test_readme_slash_command_words_and_flags_are_in_skill_md():
    flags = _skill_md_flags()
    seen = 0
    for code in _code(_readme()):
        for match in re.finditer(r"/skipwatch(?: (.*))?", code):
            args = match.group(1) or ""
            words = args.split()
            if words and re.fullmatch(r"[a-z]+", words[0]):
                assert words[0] in SLASH_WORDS, words[0]
            for flag in re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", args):
                assert flag in flags, flag
            seen += 1
    assert seen >= 3


def test_readme_flags_table_matches_skill_md():
    readme_flags = set(re.findall(r"^\| `(--[a-z-]+)", _readme(), flags=re.M))
    assert readme_flags == _skill_md_flags()


def test_docs_have_no_em_dash_personal_paths_or_emails():
    paths = [README, *ASSETS.glob("*.svg"), *DEMO.glob("*.txt")]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for bad in (EM_DASH, "/Users/", "@gmail.com", "/private/tmp"):
            assert bad not in text, (path.name, bad)


def test_readme_documents_tiers_the_engine_and_the_skill_layout():
    text = _readme()
    assert "uvx skipwatch doctor" in text and "uv tool install skipwatch" in text
    for tier in ("| 0 |", "| 1 |", "| 1c |", "| 2 |", "| 3 |"):
        assert tier in text, tier
    for tag in ("[spoken 00:58]", "[on-screen 00:33]", "[inferred]"):
        assert tag in text, tag  # the real excerpt shows the provenance tags
    assert "not affiliated" in text


def test_readme_covers_sharing_privacy_terms_and_removal():
    text = _readme()
    assert "You are responsible for complying with the terms of the platforms" in text
    assert "A pack's checksums prove the files were not changed by accident." in text
    assert "No telemetry" in text
    assert "/plugin uninstall skipwatch@skipwatch" in text and "~/.skipwatch" in text


def test_readme_claims_match_yes_test_run_and_frame_sampling():
    text = _readme()
    assert "Nothing from the video runs" not in text  # false under --test (skill-tester)
    assert "Nothing is installed until you say yes." not in text  # --yes exists
    assert text.count("or pass `--yes` and nothing is flagged") == 2
    assert "only if you ask for a test run, and then in a scratch folder" in text
    assert "scene changes" not in text  # frames.py samples 1 fps through mpdecimate
    assert "Frames sampled once a second" in text


def test_readme_states_the_session_start_hook_install():
    # the hook runs `uv sync` (network, dependency install): consent at plugin install
    text = _readme()
    install = text.split("## Install", 1)[1].split("\n## ", 1)[0]
    assert "SessionStart hook" in install and "`uv sync`" in install
    assert "300 s" in install and "PyPI" in install
    privacy = text.split("## Privacy", 1)[1].split("\n## ", 1)[0]
    assert "PyPI" in privacy


def test_readme_privacy_names_the_run_cache_and_how_to_clear_it():
    privacy = _readme().split("## Privacy", 1)[1].split("\n## ", 1)[0]
    assert "The run cache under `~/.skipwatch/cache/` keeps its own copy" in privacy
    assert "`skipwatch cache --clear` removes it" in privacy


# Install, uninstall and troubleshooting docs (M6 install docs)

TROUBLESHOOTING = ROOT / "docs/troubleshooting.md"


def _section(text: str, heading: str) -> str:
    return text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]


def test_readme_quickstart_is_near_the_top_and_complete():
    text = _readme()
    quickstart = _section(text, "Quickstart")
    assert text.index("## Quickstart") < text.index("## Why")
    assert "Claude Code" in quickstart and "uv" in quickstart
    for line in (
        "/plugin marketplace add robert-botto/skipwatch",
        "/plugin install skipwatch@skipwatch",
        "/skipwatch <video link>",
    ):
        assert line in quickstart, line


def test_readme_install_locations_match_the_code():
    where = _section(_readme(), "What gets installed where")
    # scripts/skipwatch: venv="$root/.venv"; whisper_common.hf_hub_cache; install.scope_target
    assert "`.venv`" in where and "`uv sync`" in where and "`uv cache dir`" in where
    for path in ("~/.cache/huggingface/hub", "HF_HUB_CACHE", "HF_HOME", "XDG_CACHE_HOME"):
        assert path in where, path
    for path in ("~/.claude/skills/<name>", "./.claude/skills/<name>", "./.agents/skills/<name>"):
        assert path in where, path
    # config.skipwatch_home and the folders the engine makes under it
    assert "`SKIPWATCH_HOME`" in where and "<project>/.skipwatch" in where
    for entry in ("work/", "cache/", "packs/", "backups/", "logs/", "config.toml", "installs.json"):
        assert f"`{entry}" in where, entry


def test_readme_uninstall_lists_every_step():
    uninstall = _section(_readme(), "Uninstall")
    for step in (
        "/plugin uninstall skipwatch@skipwatch",
        "/plugin marketplace remove skipwatch",  # marketplace.json name
        "~/.skipwatch",
        "<project>/.skipwatch",
        "models--Systran--faster-whisper-small",  # DEFAULT_MODELS in whisper_common.py
        "models--mlx-community--whisper-large-v3-turbo",
        "/skipwatch list",
    ):
        assert step in uninstall, step


def _wrapper_exit_codes() -> set[int]:
    """Exit codes scripts/skipwatch itself returns (the engine never ran): its fail calls."""
    text = (ROOT / "scripts/skipwatch").read_text(encoding="utf-8")
    codes = {int(code) for code in re.findall(r"\bfail\s+(\d+)", text)}
    assert codes, "no fail <code> calls found in scripts/skipwatch"
    return codes


def test_troubleshooting_table_has_every_exit_code_from_the_source():
    text = TROUBLESHOOTING.read_text(encoding="utf-8")
    rows = set(re.findall(r"^\| (\d+) \| `?([^|`]+?)`? \|", text, flags=re.M))
    for code in ExitCode:
        assert (str(code.value), code.name) in rows, code
    documented = {int(code) for code, _ in rows}
    for code in _wrapper_exit_codes():
        assert code in documented, f"wrapper exit {code}"
    assert documented == {c.value for c in ExitCode} | _wrapper_exit_codes()


def test_readme_points_to_troubleshooting():
    assert "](docs/troubleshooting.md)" in _readme()


def test_troubleshooting_links_resolve_and_text_is_clean():
    text = TROUBLESHOOTING.read_text(encoding="utf-8")
    for bad in (EM_DASH, "/Users/", "@gmail.com", "/private/tmp"):
        assert bad not in text, bad
    targets = re.findall(r"\]\(([^)\s]+)\)", FENCE.sub("", text))
    relative = [t for t in targets if not re.match(r"[a-z]+:|#", t)]
    assert relative, "troubleshooting links no local files"
    for target in relative:
        assert (TROUBLESHOOTING.parent / target.split("#")[0]).exists(), target


def test_readme_privacy_names_every_network_destination():
    privacy = _readme().split("## Privacy", 1)[1].split("\n## ", 1)[0]
    # scripts/skipwatch syncs on the first run too, not only from the SessionStart hook
    assert "the first run" in privacy
    # providers/pack_fetch.py: /skipwatch install <https url> downloads the pack
    assert "/skipwatch install <https url>" in privacy
    for destination in ("yt-dlp", "at most 5 per post", "Hugging Face", "treg", "Deepgram"):
        assert destination in privacy, destination


def test_troubleshooting_70_row_matches_the_engine():
    rows = (ROOT / "docs/troubleshooting.md").read_text(encoding="utf-8").splitlines()
    [row] = [line for line in rows if line.startswith("| 70 |")]
    cli = (ROOT / "src/skipwatch/cli.py").read_text(encoding="utf-8")
    assert "skipwatch: internal error: " in row and "skipwatch: internal error: " in cli
    assert "SKIPWATCH_DEBUG=1" in row and '"SKIPWATCH_DEBUG") == "1"' in cli
