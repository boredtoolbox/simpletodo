"""Cut the bundled Inter faces down to the scripts the app is written in.

    .venv/bin/python tools/subset_inter.py <unzipped Inter-4.1 release>

Reads the static faces from the release's extras/ttf folder and writes
ui/assets/fonts/. The full faces are ~410KB each; Latin, Latin Extended and
the punctuation the UI draws, unhinted, come to about a third of that. Text in
any other script still renders, through Qt's per-glyph fallback to a system
face.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from fontTools import subset

WEIGHTS = ("Regular", "Medium", "SemiBold", "Bold")

UNICODES = [
    "U+0000-024F",   # Basic Latin, Latin-1, Latin Extended-A and -B
    "U+1E00-1EFF",   # Latin Extended Additional (Vietnamese and the like)
    "U+2000-206F",   # General Punctuation: dashes, quotes, the ellipsis
    "U+20AC",        # euro sign
    "U+2122",        # trade mark
    "U+2190-21FF",   # arrows
    "U+2212",        # minus sign
    "U+22EF",        # midline ellipsis, the row menu glyph
]

OUT = Path(__file__).resolve().parent.parent / "simpletodo" / "ui" / "assets" / "fonts"


def main(release: Path) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    options = subset.Options()
    options.layout_features = ["*"]      # keep kerning and contextual forms
    options.name_IDs = ["*"]
    options.notdef_outline = True
    # Inter is drawn to render unhinted, and macOS ignores hints anyway.
    options.hinting = False

    for weight in WEIGHTS:
        source = release / "extras" / "ttf" / f"Inter-{weight}.ttf"
        font = subset.load_font(str(source), options)
        subsetter = subset.Subsetter(options)
        subsetter.populate(unicodes=subset.parse_unicodes(",".join(UNICODES)))
        subsetter.subset(font)
        target = OUT / f"Inter-{weight}.ttf"
        subset.save_font(font, str(target), options)
        print(f"{target.name}: {target.stat().st_size // 1024} KB")

    shutil.copy(release / "LICENSE.txt", OUT / "LICENSE.txt")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]))
