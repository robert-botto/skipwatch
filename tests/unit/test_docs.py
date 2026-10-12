"""README, demo GIF and repo graphics (plan Task M6-B1)."""

import importlib.util
import io
from pathlib import Path
from types import ModuleType

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "docs/demo"
ASSETS = ROOT / "docs/assets"
EM_DASH = chr(0x2014)


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
    import xml.etree.ElementTree as ET

    text = (ASSETS / name).read_text(encoding="utf-8")
    ET.fromstring(text)  # well-formed
    lowered = text.lower()
    assert "<image" not in lowered and "@import" not in lowered and "@font-face" not in lowered
    assert "href=\"http" not in lowered.replace("xmlns=\"http", "")
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
