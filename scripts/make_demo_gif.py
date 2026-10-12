"""Render a real run log as a typed terminal animation (plan Task M6-B1).

    uv run python scripts/make_demo_gif.py docs/demo/demo-run.txt -o docs/demo/demo.gif

The first line is the command the user typed and is typed out character by character; every
later line appears as the run printed it. 960x540, about 20 seconds, loops forever. The same
input and the same font give the same bytes. The font is the first monospace font found in
MONO_FONTS (Menlo on macOS, DejaVu Sans Mono on Linux, Consolas on Windows), or Pillow's own
font when none is found; pass --font to pin one. Characters the font lacks (the emoji in a
video title) are drawn with the system emoji font when there is one.
"""

import argparse
import sys
import textwrap
from pathlib import Path
from typing import BinaryIO

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 960, 540
FONT_SIZE = 16
LINE_HEIGHT = 20
PAD_X = 24
BAR_HEIGHT = 34
TOP = BAR_HEIGHT + 12

MONO_FONTS = [
    "/System/Library/Fonts/Menlo.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "C:/Windows/Fonts/consola.ttf",
]
EMOJI_FONTS = ["/System/Library/Fonts/Apple Color Emoji.ttc"]
EMOJI_SOURCE_SIZE = 20  # Apple Color Emoji is a bitmap font with fixed sizes

BG = (13, 17, 23)
BAR = (27, 33, 41)
FG = (230, 237, 243)
DIM = (139, 148, 158)
ACCENT = (217, 119, 87)
GREEN = (63, 185, 80)
DOTS = [(255, 95, 86), (255, 189, 46), (39, 201, 63)]

# Timing in milliseconds.
START_MS = 700
TYPE_CHARS = 2
TYPE_MS = 40
AFTER_ENTER_MS = 900
LINE_MS = 600
BLANK_MS = 200
SLOW_LINE_MS = 1400  # a line that stands for a stage that takes a while (installing)
END_MS = 7000

Span = tuple[str, tuple[int, int, int]]


def _font(path: str | None) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in [path] if path else MONO_FONTS:
        if candidate and Path(candidate).exists():
            return ImageFont.truetype(candidate, FONT_SIZE)
    if path:
        sys.exit(f"font not found: {path}")
    return ImageFont.load_default(size=FONT_SIZE)


def _emoji_font() -> ImageFont.FreeTypeFont | None:
    for candidate in EMOJI_FONTS:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, EMOJI_SOURCE_SIZE)
    return None


def _palette() -> Image.Image:
    """A fixed palette: each text colour with an anti-aliasing ramp down to the background."""
    colours = [BG, BAR, *DOTS]
    for colour in (FG, DIM, ACCENT, GREEN):
        for step in range(1, 9):
            pairs = zip(BG, colour, strict=True)
            colours.append(tuple(round(b + (c - b) * step / 8) for b, c in pairs))
    flat = [value for colour in colours for value in colour]
    image = Image.new("P", (1, 1))
    image.putpalette(flat + [0] * (768 - len(flat)))
    return image


def _spans(line: str) -> list[Span]:
    """Colour one log line: the prompt, the review screen labels, the install result."""
    if line.startswith("> "):
        return [("> ", ACCENT), (line[2:], FG)]
    if line.startswith("Installed to "):
        return [(line, GREEN)]
    if line.startswith("This skill credits "):
        return [(line, DIM)]
    if line.startswith("  ") and ":" in line:
        label, rest = line.split(":", 1)
        return [(label + ":", DIM), (rest, FG)]
    return [(line, FG)]


def _wrap(line: str, columns: int) -> list[str]:
    if len(line) <= columns:
        return [line]
    indent = " " * (len(line) - len(line.lstrip(" ")) + 2)
    return textwrap.wrap(
        line, width=columns, subsequent_indent=indent, break_on_hyphens=False, drop_whitespace=True
    )


def _wrapped_spans(line: str, columns: int) -> list[list[Span]]:
    """Wrap a line by columns and carry each character's colour onto its display row."""
    colours = [colour for text, colour in _spans(line) for _ in text]
    rows: list[list[Span]] = []
    position = 0
    for row in _wrap(line, columns):
        stripped = row.lstrip(" ")
        start = line.index(stripped, position)
        indent = row[: len(row) - len(stripped)]
        spans: list[Span] = [(indent, FG)] if indent else []
        for offset, char in enumerate(stripped):
            colour = colours[start + offset]
            if spans and spans[-1][1] == colour:
                spans[-1] = (spans[-1][0] + char, colour)
            else:
                spans.append((char, colour))
        rows.append(spans)
        position = start + len(stripped)
    return rows or [[]]


class Painter:
    def __init__(self, font_path: str | None = None) -> None:
        self.font = _font(font_path)
        self.emoji = _emoji_font()
        self.char_width = self.font.getlength("M")
        self.columns = int((WIDTH - 2 * PAD_X) // self.char_width)
        self.rows = (HEIGHT - TOP - 8) // LINE_HEIGHT
        self.palette = _palette()
        self._missing = self._glyph("\U0010ffff")

    def _glyph(self, char: str) -> bytes:
        image = Image.new("L", (FONT_SIZE * 2, FONT_SIZE * 2))
        ImageDraw.Draw(image).text((0, 0), char, font=self.font, fill=255)
        return image.tobytes()

    def _has_glyph(self, char: str) -> bool:
        return char.isspace() or self._glyph(char) != self._missing

    def _draw_text(self, image: Image.Image, x: float, y: int, text: str, colour) -> float:
        draw = ImageDraw.Draw(image)
        for char in text:
            if self.emoji is not None and not self._has_glyph(char):
                glyph = Image.new("RGBA", (EMOJI_SOURCE_SIZE * 2, EMOJI_SOURCE_SIZE * 2))
                ImageDraw.Draw(glyph).text((0, 0), char, font=self.emoji, embedded_color=True)
                box = glyph.getbbox()
                if box:
                    glyph = glyph.crop(box).resize((FONT_SIZE, FONT_SIZE), Image.Resampling.LANCZOS)
                    image.paste(glyph, (round(x), y + 2), glyph)
                x += self.char_width * 2
                continue
            draw.text((x, y), char, font=self.font, fill=colour)
            x += self.char_width
        return x

    def frame(self, rows: list[list[Span]], cursor: bool) -> Image.Image:
        image = Image.new("RGB", (WIDTH, HEIGHT), BG)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, WIDTH, BAR_HEIGHT), fill=BAR)
        for index, colour in enumerate(DOTS):
            cx = 22 + index * 20
            draw.ellipse((cx - 6, BAR_HEIGHT // 2 - 6, cx + 6, BAR_HEIGHT // 2 + 6), fill=colour)
        title = "~ claude"
        title_x = (WIDTH - self.font.getlength(title)) / 2
        draw.text((title_x, BAR_HEIGHT // 2 - FONT_SIZE // 2 - 1), title, font=self.font, fill=DIM)
        visible = rows[-self.rows :]
        end_x: float = PAD_X
        y = TOP
        for spans in visible:
            x: float = PAD_X
            for text, colour in spans:
                x = self._draw_text(image, x, y, text, colour)
            end_x = x
            y += LINE_HEIGHT
        if cursor:
            cy = TOP + (len(visible) - 1) * LINE_HEIGHT
            box = (end_x + 1, cy + 1, end_x + self.char_width - 1, cy + FONT_SIZE + 2)
            draw.rectangle(box, fill=FG)
        return image.quantize(palette=self.palette, dither=Image.Dither.NONE)


def render(lines: list[str], out: BinaryIO, font_path: str | None = None) -> None:
    painter = Painter(font_path)
    frames: list[Image.Image] = []
    durations: list[int] = []

    def add(rows: list[list[Span]], ms: int, cursor: bool = False) -> None:
        frames.append(painter.frame(rows, cursor))
        durations.append(ms)

    command, rest = lines[0], lines[1:]
    add([[("> ", ACCENT)]], START_MS, cursor=True)
    for end in range(2 + TYPE_CHARS, len(command) + TYPE_CHARS, TYPE_CHARS):
        add(_wrapped_spans(command[:end], painter.columns), TYPE_MS, cursor=True)
    rows = _wrapped_spans(command, painter.columns)
    add(rows, AFTER_ENTER_MS)
    for line in rest:
        rows = rows + _wrapped_spans(line, painter.columns)
        if not line.strip():
            ms = BLANK_MS
        elif line.startswith("Installing"):
            ms = SLOW_LINE_MS
        else:
            ms = LINE_MS
        add(rows, ms)
    durations[-1] = END_MS
    frames[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=False,
        disposal=1,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("log", type=Path, help="The run log; its first line is the command.")
    parser.add_argument("-o", "--out", type=Path, required=True, help="The GIF to write.")
    parser.add_argument("--font", help="A monospace .ttf or .ttc to use instead of the default.")
    args = parser.parse_args()
    lines = args.log.read_text(encoding="utf-8").splitlines()
    with args.out.open("wb") as out:
        render(lines, out, args.font)
    print(f"Wrote {args.out} ({args.out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
