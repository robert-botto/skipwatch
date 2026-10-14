"""Render GitHub's social preview card for the repository (1280x640 PNG).

    uv run python scripts/make_social_preview.py -o docs/assets/social-preview.png

Upload the file by hand in the repository's Settings, under Social preview. The card text
uses only Pillow's bundled font. The falling code rain behind it needs a font with half-width
katakana: pass one with --rain-font, or the script uses Hiragino Kaku Gothic W3, which macOS
ships. Without a usable font the script stops instead of rendering a card without rain. The
rain is seeded, so the output is byte-identical only when the same font file is used.
"""

import argparse
import math
import random
import sys
from functools import cache
from pathlib import Path
from typing import BinaryIO

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

WIDTH, HEIGHT = 1280, 640
BG = (13, 17, 23)
BORDER = (48, 54, 61)
FG = (230, 237, 243)
DIM = (145, 152, 161)
ACCENT = (224, 138, 104)
CHIP = (43, 29, 23)

TAGLINE = "Paste a video. Claude knows kung fu."
PITCH = "A Claude Code plugin that turns a tutorial video into an installed skill."
COMMAND = "/skipwatch <video link>"

MACOS_RAIN_FONT = Path("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc")
RAIN_SEED = 5
GLYPH_SIZE = 15
PITCH_X, PITCH_Y = 20, 19
ACTIVE_SHARE = 0.4  # share of columns that carry a trail
FG_SHARE = 0.15  # share of active columns drawn in FG instead of ACCENT
HEAD_ALPHA = 0.55
TRAIL_ALPHA = 0.30  # the trail fades from this to 0
FG_ALPHA = 0.10
GLYPHS = [chr(c) for c in range(0xFF66, 0xFF9E)] + list("0123456789") * 2 + list("ZXKSWAE")
KATAKANA_PROBES = ["ｦ", "ｱ", "ﾊ", "ﾝ"]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _centered(draw: ImageDraw.ImageDraw, y: int, text: str, font, fill) -> None:
    width = draw.textlength(text, font=font)
    draw.text(((WIDTH - width) / 2, y), text, font=font, fill=fill)


def render_plain() -> Image.Image:
    """The card without rain."""
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    title = _font(132)
    skip, watch = "Skip", "Watch"
    total = draw.textlength(skip + watch, font=title)
    x = (WIDTH - total) / 2
    draw.text((x, 112), skip, font=title, fill=FG, stroke_width=3, stroke_fill=FG)
    x += draw.textlength(skip, font=title)
    draw.text((x, 112), watch, font=title, fill=ACCENT, stroke_width=3, stroke_fill=ACCENT)

    _centered(draw, 292, TAGLINE, _font(46), FG)
    _centered(draw, 360, PITCH, _font(28), DIM)

    command = _font(30)
    pad_x, pad_y = 30, 18
    width = draw.textlength(COMMAND, font=command)
    left = (WIDTH - width) / 2 - pad_x
    top = 452
    box = (left, top, left + width + 2 * pad_x, top + 30 + 2 * pad_y)
    draw.rounded_rectangle(box, radius=33, fill=CHIP, outline=ACCENT, width=2)
    _centered(draw, top + pad_y - 2, COMMAND, command, ACCENT)

    draw.rounded_rectangle((24, 24, WIDTH - 24, HEIGHT - 24), radius=28, outline=BORDER, width=2)
    return image


def _glyph_bitmap(font: ImageFont.FreeTypeFont, char: str) -> bytes:
    image = Image.new("L", (40, 40))
    ImageDraw.Draw(image).text((4, 4), char, font=font, fill=255)
    return image.tobytes()


def has_katakana(path: Path) -> bool:
    """True if the font draws distinct half-width katakana, not empty or missing-glyph boxes."""
    try:
        font = ImageFont.truetype(str(path), GLYPH_SIZE)
    except OSError:
        return False
    missing = _glyph_bitmap(font, "\U000f0000")  # a private-use code point no font draws
    probes = [_glyph_bitmap(font, char) for char in KATAKANA_PROBES]
    drawn = all(any(probe) and probe != missing for probe in probes)
    return drawn and len(set(probes)) == len(probes)


def find_rain_font(explicit: Path | None = None) -> Path | None:
    """The rain font: the one passed in, else the macOS system font, if it has katakana."""
    candidate = explicit if explicit is not None else MACOS_RAIN_FONT
    return candidate if candidate.is_file() and has_katakana(candidate) else None


def _smoothstep(lo: float, hi: float, x: float) -> float:
    t = min(1.0, max(0.0, (x - lo) / (hi - lo)))
    return t * t * (3 - 2 * t)


@cache
def _vignette_mask() -> Image.Image:
    ax, ay = 0.31 * WIDTH, 0.26 * HEIGHT
    mask = Image.new("L", (WIDTH, HEIGHT))
    pixels = mask.load()
    assert pixels is not None
    for y in range(HEIGHT):
        dy = (y + 0.5 - HEIGHT / 2) / ay
        for x in range(WIDTH):
            dx = (x + 0.5 - WIDTH / 2) / ax
            pixels[x, y] = round(255 * _smoothstep(1.0, 1.4, math.hypot(dx, dy)))
    return mask


def _vignette() -> Image.Image:
    """0 inside the central ellipse (62% x 52% of the card), rising to 1 toward the edges."""
    return _vignette_mask()


def _clearance(drawn: Image.Image) -> Image.Image:
    """0 in a feathered 12 px halo around everything drawn inside the border."""
    inner = Image.new("L", drawn.size, 0)
    ImageDraw.Draw(inner).rectangle((36, 36, WIDTH - 36, HEIGHT - 36), fill=255)
    halo = ImageChops.multiply(drawn, inner).filter(ImageFilter.MaxFilter(25))
    halo = halo.filter(ImageFilter.GaussianBlur(6)).point(lambda v: min(255, v * 3))
    return ImageChops.invert(halo)


def _rain_layer(font_path: Path) -> Image.Image:
    rng = random.Random(RAIN_SEED)
    font = ImageFont.truetype(str(font_path), GLYPH_SIZE)
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    rows = HEIGHT // PITCH_Y + 1
    for column in range(WIDTH // PITCH_X):
        if rng.random() >= ACTIVE_SHARE:
            continue
        dim_fg = rng.random() < FG_SHARE
        head = rng.randrange(0, rows + 8)
        length = rng.randint(8, 20)
        center_x = column * PITCH_X + PITCH_X / 2
        for i in range(length):
            row = head - i
            if row < 0:
                break
            if row >= rows:
                continue
            if dim_fg:
                color, alpha = FG, FG_ALPHA * (1 - i / length)
            elif i == 0:
                color, alpha = ACCENT, HEAD_ALPHA
            else:
                color, alpha = ACCENT, TRAIL_ALPHA * (1 - (i - 1) / (length - 1))
            glyph = rng.choice(GLYPHS)
            x = center_x - draw.textlength(glyph, font=font) / 2
            draw.text((x, row * PITCH_Y), glyph, font=font, fill=(*color, round(255 * alpha)))
    return layer


def add_rain(card: Image.Image, font_path: Path) -> Image.Image:
    """The card with rain on its bare background only: every drawn pixel stays as it was."""
    drawn = ImageChops.difference(card, Image.new("RGB", card.size, BG)).convert("L")
    drawn = drawn.point(lambda v: 255 if v else 0)
    clip = Image.new("L", card.size, 0)  # keep the rain inside the border
    ImageDraw.Draw(clip).rounded_rectangle((30, 30, WIDTH - 30, HEIGHT - 30), radius=24, fill=255)

    layer = _rain_layer(font_path)
    alpha = ImageChops.multiply(layer.getchannel("A"), _vignette())
    alpha = ImageChops.multiply(alpha, clip)
    layer.putalpha(ImageChops.multiply(alpha, _clearance(drawn)))
    background = Image.new("RGBA", card.size, (*BG, 255))
    background.alpha_composite(layer)
    return Image.composite(background.convert("RGB"), card, ImageChops.invert(drawn))


def render(out: BinaryIO, rain_font: Path) -> None:
    add_rain(render_plain(), rain_font).save(out, format="PNG", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-o", "--out", type=Path, required=True, help="The PNG to write.")
    parser.add_argument(
        "--rain-font",
        type=Path,
        help="A font with half-width katakana for the rain (default: the macOS system font).",
    )
    args = parser.parse_args()
    font = find_rain_font(args.rain_font)
    if font is None:
        tried = args.rain_font or MACOS_RAIN_FONT
        print(
            f"No usable rain font: {tried} is missing or has no half-width katakana. "
            "Pass --rain-font with a font that has them.",
            file=sys.stderr,
        )
        sys.exit(1)
    with args.out.open("wb") as out:
        render(out, font)
    print(f"Wrote {args.out} ({args.out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
