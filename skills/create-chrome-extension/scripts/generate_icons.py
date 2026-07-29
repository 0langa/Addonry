#!/usr/bin/env python3
"""Generate dependency-free PNG icons for a personal Chrome extension."""

from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def parse_hex_color(value: str) -> tuple[int, int, int]:
    normalized = value.removeprefix("#")
    if len(normalized) != 6:
        raise ValueError("color must be six hexadecimal digits")
    return tuple(int(normalized[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def png_bytes(size: int, color: tuple[int, int, int]) -> bytes:
    if size < 8:
        raise ValueError("icon size must be at least 8")

    background = (*color, 255)
    foreground = (255, 255, 255, 255)
    border = max(1, size // 12)
    inset = max(2, size // 5)
    pixels = bytearray()

    for y in range(size):
        pixels.append(0)  # PNG filter type: none
        for x in range(size):
            on_diagonal = abs((x - y)) <= border or abs((x + y) - (size - 1)) <= border
            in_mark = inset <= x < size - inset and inset <= y < size - inset and on_diagonal
            pixels.extend(foreground if in_mark else background)

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return PNG_SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(bytes(pixels), 9)) + _chunk(b"IEND", b"")


def generate_icons(output_dir: Path, color: str = "#7C3AED") -> list[Path]:
    rgb = parse_hex_color(color)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for size in (16, 32, 48, 128):
        path = output_dir / f"icon{size}.png"
        path.write_bytes(png_bytes(size, rgb))
        paths.append(path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--color", default="#7C3AED")
    args = parser.parse_args()
    for path in generate_icons(args.output_dir, args.color):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
