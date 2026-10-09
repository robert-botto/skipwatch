import re

from PIL import Image, ImageChops, ImageDraw

from skipwatch.dhash import DUPLICATE_DISTANCE, dhash, hamming


def _text_on_black(size=(320, 180)) -> Image.Image:
    img = Image.new("RGB", size, "black")
    draw = ImageDraw.Draw(img)
    for row in range(4):
        draw.rectangle((20, 20 + row * 40, 60 + row * 60, 40 + row * 40), fill="white")
    return img


def _gradient(size=(320, 180)) -> Image.Image:
    img = Image.new("L", size)
    img.putdata([(x * 7 + y * 3) % 256 for y in range(size[1]) for x in range(size[0])])
    return img.convert("RGB")


def test_different_images_are_not_duplicates():
    black = Image.new("RGB", (320, 180), "black")
    assert hamming(dhash(black), dhash(_text_on_black())) > DUPLICATE_DISTANCE


def test_identical_images_distance_zero():
    img = _text_on_black()
    assert hamming(dhash(img), dhash(img.copy())) == 0


def test_two_pixel_shift_is_a_duplicate():
    img = _gradient()
    shifted = ImageChops.offset(img, 2, 0)
    assert hamming(dhash(img), dhash(shifted)) <= DUPLICATE_DISTANCE


def test_hash_is_16_hex_chars():
    assert re.fullmatch(r"[0-9a-f]{16}", dhash(_text_on_black()))


def test_hamming_counts_differing_bits():
    assert hamming("0" * 16, "0" * 15 + "3") == 2
    assert hamming("f" * 16, "0" * 16) == 64
