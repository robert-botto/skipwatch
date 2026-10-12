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
