"""Application entry point: wire storage to the window, then run."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from . import paths
from .database import Database, DatabaseError
from .store import TodoStore
from .ui.main_window import MainWindow
from .ui.style import stylesheet

log = logging.getLogger(__name__)


def _fatal(message: str) -> int:
    """Report a startup failure through the GUI if we can, else the console."""
    if QApplication.instance() is not None:
        box = QMessageBox()
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("SimpleTodo cannot start")
        box.setText(message)
        box.exec()
    print(f"SimpleTodo cannot start:\n{message}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    # Reuse an instance when one exists, so the app can be driven from tests.
    app = QApplication.instance() or QApplication(
        argv if argv is not None else sys.argv
    )
    app.setApplicationName("SimpleTodo")
    app.setApplicationDisplayName("SimpleTodo")
    app.setStyle("Fusion")
    app.setStyleSheet(stylesheet())

    try:
        paths.ensure_data_dir()
    except OSError as exc:
        return _fatal(
            f"The data folder could not be prepared.\n\n{exc}\n\n"
            f"Expected location: {paths.data_dir()}"
        )

    db = Database()
    try:
        db.connect()
    except DatabaseError as exc:
        return _fatal(str(exc))

    store = TodoStore(db)
    window = MainWindow(store)
    window.show()

    if db.recovered_from is not None:
        window.notify(
            "Database rebuilt",
            "The existing database could not be read, so it was set aside and "
            "a new empty one was created.\n\n"
            f"The damaged file is kept at:\n{db.recovered_from}",
        )

    try:
        return app.exec()
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
