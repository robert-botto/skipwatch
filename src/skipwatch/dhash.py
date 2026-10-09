"""Difference hash (dHash) with Pillow only: 64 bits as 16 hex characters."""

from PIL import Image

DUPLICATE_DISTANCE = 6


def dhash(image: Image.Image) -> str:
    """Grayscale, resize to 9x8, one bit per pixel pair (left brighter than right), row-major."""
    small = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = small.tobytes()  # one byte per pixel in mode L
    bits = 0
    for row in range(8):
        for col in range(8):
            left = pixels[row * 9 + col]
            right = pixels[row * 9 + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()
