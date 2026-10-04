#!/usr/bin/env python3
"""Generate the tileable paper grain used as the application background.

Run from the project root to regenerate the asset:

    .venv/bin/python tools/make_paper_texture.py

The grain is per-pixel and uncorrelated, which is what makes the tile seam
invisible: neighbouring pixels share no structure, so no edge can line up.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

from PySide6.QtGui import QColor, QImage, qRgb

#: Tile side in pixels. Large enough that repetition is not readable.
SIZE = 192

#: The paper itself: a warm off-white, never pure white.
BASE = QColor("#FAF7F0")

#: How far each pixel may stray from the base, per channel. Kept tiny: the
#: grain should be felt rather than seen.
GRAIN = 3

#: A handful of slightly darker specks per tile, like flecks in the pulp.
FLECKS = 60
FLECK_DEPTH = 6


def build(seed: int = 7) -> QImage:
    rng = random.Random(seed)
    image = QImage(SIZE, SIZE, QImage.Format_RGB32)
    red, green, blue = BASE.red(), BASE.green(), BASE.blue()

    for y in range(SIZE):
        for x in range(SIZE):
            # One shared offset per pixel keeps the paper neutral; varying the
            # channels independently would tint the grain.
            offset = rng.randint(-GRAIN, GRAIN)
            image.setPixel(
                x,
                y,
                qRgb(
                    max(0, min(255, red + offset)),
                    max(0, min(255, green + offset)),
                    max(0, min(255, blue + offset)),
                ),
            )

    for _ in range(FLECKS):
        x, y = rng.randrange(SIZE), rng.randrange(SIZE)
        depth = rng.randint(2, FLECK_DEPTH)
        colour = qRgb(
            max(0, red - depth), max(0, green - depth), max(0, blue - depth)
        )
        image.setPixel(x, y, colour)

    return image


def main() -> int:
    target = Path(__file__).resolve().parent.parent / "simpletodo" / "ui" / "assets"
    target.mkdir(parents=True, exist_ok=True)
    path = target / "paper.png"
    if not build().save(str(path), "PNG"):
        print(f"could not write {path}", file=sys.stderr)
        return 1
    print(f"wrote {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
