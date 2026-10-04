#!/usr/bin/env python3
"""Build the macOS app icon from the source artwork.

Run from the project root to regenerate the asset:

    .venv/bin/python tools/make_app_icon.py

The source is a JPEG, so its rounded corners are solid white rather than
transparent, and the artwork runs edge to edge. macOS icons sit inside a
margin on a 1024px grid (an 824px tile), so the artwork is clipped to a rounded
square and placed on that grid. Without both, the Dock shows a white-cornered
square that looks larger than every icon beside it.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QPainterPath

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "simpletodoappimage.jpg"
OUTPUT = ROOT / "packaging" / "SimpleTodo.icns"

#: Apple's icon grid: a 1024px canvas holding an 824px tile.
CANVAS = 1024
TILE = 824

#: Corner radius as a share of the tile side. Slightly rounder than the
#: artwork's own corners, so the clip cuts inside the blue and no white
#: fringe from the JPEG survives along the curve.
CORNER = 0.235

#: Source pixels shaved off every side. The JPEG's blue fades into white over
#: its outermost few pixels, which showed as a pale rim along the straight
#: edges once the background turned transparent.
TRIM = 12

#: Every size iconutil expects in an .iconset, as (name, pixels).
SIZES = [
    (f"icon_{side}x{side}{suffix}.png", side * scale)
    for side in (16, 32, 128, 256, 512)
    for scale, suffix in ((1, ""), (2, "@2x"))
]


def master() -> QImage:
    art = QImage(str(SOURCE))
    if art.isNull():
        raise SystemExit(f"Cannot read {SOURCE}")

    canvas = QImage(CANVAS, CANVAS, QImage.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.transparent)

    offset = (CANVAS - TILE) / 2
    tile = QRectF(offset, offset, TILE, TILE)
    clip = QPainterPath()
    clip.addRoundedRect(tile, TILE * CORNER, TILE * CORNER)

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.setClipPath(clip)
    source = QRectF(art.rect()).adjusted(TRIM, TRIM, -TRIM, -TRIM)
    painter.drawImage(tile, art, source)
    painter.end()
    return canvas


def main() -> int:
    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    image = master()

    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "SimpleTodo.iconset"
        iconset.mkdir()
        for name, pixels in SIZES:
            scaled = image.scaled(
                pixels, pixels, Qt.IgnoreAspectRatio, Qt.SmoothTransformation
            )
            scaled.save(str(iconset / name))

        OUTPUT.parent.mkdir(exist_ok=True)
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(OUTPUT)],
            check=True,
        )
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
