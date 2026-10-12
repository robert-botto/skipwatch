"""Render GitHub's social preview card for the repository (1280x640 PNG).

    uv run python scripts/make_social_preview.py -o docs/assets/social-preview.png

Upload the file by hand in the repository's Settings, under Social preview. It uses only
Pillow's bundled font, so every machine renders the same bytes.
"""

import argparse
from pathlib import Path
from typing import BinaryIO

from PIL import Image, ImageDraw, ImageFont

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


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _centered(draw: ImageDraw.ImageDraw, y: int, text: str, font, fill) -> None:
    width = draw.textlength(text, font=font)
    draw.text(((WIDTH - width) / 2, y), text, font=font, fill=fill)


def render(out: BinaryIO) -> None:
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
    image.save(out, format="PNG", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-o", "--out", type=Path, required=True, help="The PNG to write.")
    args = parser.parse_args()
    with args.out.open("wb") as out:
        render(out)
    print(f"Wrote {args.out} ({args.out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
