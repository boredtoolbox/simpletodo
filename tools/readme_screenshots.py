"""Render the README screenshots from the real window.

    .venv/bin/python tools/readme_screenshots.py [out_dir]   # default: docs/

Fills a throwaway database with sample tasks, dated relative to today, and
grabs the window at 2x on Qt's offscreen platform: docs/pinned.png,
docs/project.png and docs/date.png. Your own data is never touched.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

# Before Qt is imported: offscreen needs no display, and 2x matches Retina.
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_SCALE_FACTOR"] = "2"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from simpletodo.database import Database  # noqa: E402
from simpletodo.dates import Bucket  # noqa: E402
from simpletodo.store import TodoStore  # noqa: E402
from simpletodo.ui.main_window import MainWindow  # noqa: E402
from simpletodo.ui.style import stylesheet  # noqa: E402
from simpletodo.ui.views import Mode  # noqa: E402

#: name, days from today, project (None: the Inbox)
TASKS = [
    ("Book the Enkoji autumn viewing", 0, "Japan Trip"),
    ("Reserve the JR pass", 1, "Japan Trip"),
    ("Confirm Kyoto hotel", 8, "Japan Trip"),
    ("Pack bags", -2, "Japan Trip"),
    ("Call the plumber", -3, "Home Chores"),
    ("Wash the dishes", 0, "Home Chores"),
    ("Finish The Remains of the Day", 12, "Reading List"),
    ("Return the library parcel", 0, None),
    ("Renew passport photo", 3, None),
]
DONE = {"Pack bags", "Wash the dishes"}
PINNED = {"Reserve the JR pass", "Call the plumber", "Renew passport photo"}

#: The macOS title bar's height; offscreen has none to measure.
TITLE_BAR = 32
#: Shown in the status bar instead of the throwaway database's temp path.
DATA_PATH = "~/Library/Application Support/simpletodo/todo.sqlite3"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs"
    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(stylesheet())

    db = Database(Path(tempfile.mkdtemp()) / "todo.sqlite3")
    db.connect()
    store = TodoStore(db)
    projects = {
        name: store.create_project(name)
        for name in sorted({p for _, _, p in TASKS if p})
    }
    for name, days, project in TASKS:
        due = (date.today() + timedelta(days=days)).isoformat()
        task = store.create_task(name, due, projects[project].id if project else None)
        if name in DONE:
            store.set_task_completed(task.id, True)
        if name in PINNED:
            store.set_task_pinned(task.id, True)

    window = MainWindow(store)
    window.resize(860, 560)
    window.show()
    window._set_top_bar_height(TITLE_BAR)
    window.db_path_label.setText(DATA_PATH)

    def shot(name: str) -> None:
        for _ in range(40):
            app.processEvents()
        window.grab().save(str(out / name))
        print(out / name)

    shot("pinned.png")                      # what the window opens on
    window.browser.select(projects["Japan Trip"].id)
    shot("project.png")
    window.show_mode(Mode.DATE)
    window.browser.select(Bucket.TODAY)
    shot("date.png")
    window.close()
    db.close()


if __name__ == "__main__":
    main()
