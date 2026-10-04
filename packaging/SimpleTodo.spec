# PyInstaller recipe for the double-clickable macOS app.
#
#     .venv/bin/python -m PyInstaller packaging/SimpleTodo.spec --noconfirm
#
# Produces dist/SimpleTodo.app: Python, Qt and the app in one bundle, so it
# runs with no venv and from any folder. Regenerate the icon first with
# tools/make_app_icon.py if the artwork changes.

from pathlib import Path

ROOT = Path(SPECPATH).parent

import sys
sys.path.insert(0, str(ROOT))
from simpletodo import __version__  # noqa: E402

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    # style.py reads these beside itself, so they keep their package path.
    datas=[(str(ROOT / "simpletodo" / "ui" / "assets"), "simpletodo/ui/assets")],
    # Nothing here uses them; leaving them out keeps the bundle smaller.
    excludes=["tkinter", "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick"],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SimpleTodo",
    console=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name="SimpleTodo")

app = BUNDLE(
    coll,
    name="SimpleTodo.app",
    icon=str(ROOT / "packaging" / "SimpleTodo.icns"),
    bundle_identifier="local.simpletodo",
    version=__version__,
    info_plist={
        "CFBundleDisplayName": "SimpleTodo",
        "CFBundleShortVersionString": __version__,
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.productivity",
    },
)
