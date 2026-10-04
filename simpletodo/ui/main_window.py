"""The application window: two tabs, a + button, and a quiet status bar."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..store import TodoStore
from .dialogs import CreateProjectDialog, CreateTaskDialog
from .style import SPACE_1, SPACE_2, SPACE_3, archive_icon_svg
from .widgets import ElidedLabel, restyle, rounded_menu, svg_icon
from .views import DateView, ProjectsView

APP_TITLE = "Simple To Do"
ADD_BUTTON_SIZE = 34
ARCHIVE_ICON_SIZE = 18
MIN_WIDTH = 600
MIN_HEIGHT = 440


class MainWindow(QMainWindow):
    def __init__(self, store: TodoStore) -> None:
        super().__init__()
        self.store = store

        self.setWindowTitle("SimpleTodo")
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)
        self.resize(680, 560)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setDrawBase(False)

        self.projects_view = ProjectsView(store)
        self.date_view = DateView(store)
        self.tabs.addTab(self.projects_view, "Projects")
        self.tabs.addTab(self.date_view, "Date")
        # Centre the two tab labels over the content column.
        self.tabs.tabBar().setStyleSheet("QTabBar { alignment: center; }")

        self.add_button = QPushButton("+")
        self.add_button.setObjectName("addButton")
        self.add_button.setFixedSize(ADD_BUTTON_SIZE, ADD_BUTTON_SIZE)
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.setToolTip("Create a project or a task")
        self.add_button.clicked.connect(self._show_add_menu)

        # Sits under the +, a toggle between the tabs and the archive.
        self.archive_button = QPushButton()
        self.archive_button.setObjectName("archiveButton")
        self.archive_button.setCheckable(True)
        self.archive_button.setFixedSize(ADD_BUTTON_SIZE, ADD_BUTTON_SIZE)
        self.archive_button.setIcon(svg_icon(archive_icon_svg(), ARCHIVE_ICON_SIZE))
        self.archive_button.setIconSize(QSize(ARCHIVE_ICON_SIZE, ARCHIVE_ICON_SIZE))
        self.archive_button.setCursor(Qt.PointingHandCursor)
        self.archive_button.toggled.connect(self.show_archive)

        self.archive_view = ProjectsView(store, archived=True)
        self.archive_view.setVisible(False)
        self.archive_heading = QLabel("Archive")
        self.archive_heading.setObjectName("archiveHeading")
        self.archive_heading.setVisible(False)
        self.tabs.tabBar().tabBarClicked.connect(self._on_tab_clicked)
        leave = QShortcut(QKeySequence(Qt.Key_Escape), self)
        leave.activated.connect(lambda: self.show_archive(False))

        # The + sits top left; an equally wide spacer on the right keeps the
        # tab labels centred in the window rather than centred in what is left.
        spacer = QWidget()
        spacer.setFixedWidth(ADD_BUTTON_SIZE)

        # The masthead lives outside the tab widget, so it stays put whichever
        # tab is open.
        self.title_label = QLabel(APP_TITLE)
        self.title_label.setObjectName("appTitle")
        self.title_label.setAlignment(Qt.AlignCenter)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(SPACE_3, SPACE_2, SPACE_3, 0)
        title_row.setSpacing(0)
        title_row.addWidget(self.add_button, 0, Qt.AlignLeft | Qt.AlignVCenter)
        title_row.addStretch(1)
        title_row.addWidget(self.title_label, 0, Qt.AlignHCenter)
        title_row.addStretch(1)
        title_row.addWidget(spacer)

        tab_spacer = QWidget()
        tab_spacer.setFixedWidth(ADD_BUTTON_SIZE)

        tab_row = QHBoxLayout()
        tab_row.setContentsMargins(SPACE_3, SPACE_1, SPACE_3, 0)
        tab_row.setSpacing(0)
        tab_row.addWidget(self.archive_button, 0, Qt.AlignLeft | Qt.AlignVCenter)
        tab_row.addStretch(1)
        tab_row.addWidget(self.tabs.tabBar(), 0, Qt.AlignHCenter)
        tab_row.addWidget(self.archive_heading, 0, Qt.AlignHCenter)
        tab_row.addStretch(1)
        tab_row.addWidget(tab_spacer)

        central = QWidget()
        central.setObjectName("appBackdrop")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, SPACE_3, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(title_row)
        layout.addLayout(tab_row)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.archive_view, 1)
        self.setCentralWidget(central)

        status = QStatusBar()
        status.setSizeGripEnabled(False)
        self.setStatusBar(status)

        # Counts on the left, the database location on the right. The counts
        # are a widget rather than showMessage(): a message is painted over the
        # bar without taking layout space, so the path would run underneath it.
        self.counts_label = QLabel()
        self.counts_label.setObjectName("statusText")
        status.addWidget(self.counts_label)

        db_path = store.database_path
        self.db_path_label = ElidedLabel(_display_path(db_path))
        self.db_path_label.setObjectName("statusText")
        self.db_path_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.db_path_label.setToolTip(str(db_path))
        status.addPermanentWidget(self.db_path_label, 1)

        self.show_archive(False)
        store.projectsChanged.connect(self._refresh_status)
        store.tasksChanged.connect(self._refresh_status)
        store.errorOccurred.connect(self.show_error)
        self._refresh_status()

    # -- the + menu -----------------------------------------------------

    def _show_add_menu(self) -> None:
        menu = rounded_menu(self)
        new_project = QAction("Create Project", self)
        new_project.triggered.connect(self.create_project)
        new_task = QAction("Create Task", self)
        new_task.triggered.connect(self.create_task)
        menu.addAction(new_project)
        menu.addAction(new_task)

        # Hangs below the button, which now sits at the top of the window.
        anchor = self.add_button.mapToGlobal(QPoint(0, self.add_button.height()))
        menu.popup(anchor + QPoint(0, SPACE_1))

    def show_archive(self, shown: bool) -> None:
        """Swap the tab pages for the archive, or back.

        The tab labels stay on screen with Archive beside them, so the way
        back is the obvious one: click Projects or Date. Hiding them left only
        the highlighted box button, which nobody read as "back".
        """
        self.archive_button.setChecked(shown)
        self.tabs.setVisible(not shown)
        self.archive_view.setVisible(shown)
        self.archive_heading.setVisible(shown)
        tab_bar = self.tabs.tabBar()
        tab_bar.setProperty("archiveOpen", shown)
        restyle(tab_bar)
        self.archive_button.setToolTip(
            "Back to your projects" if shown else "Show archived projects"
        )

    def _on_tab_clicked(self, index: int) -> None:
        # tabBarClicked fires for the current tab too, which is the one most
        # likely to be clicked to leave the archive.
        if index >= 0:
            self.show_archive(False)
            # Set explicitly: a click on the other tab while the archive was
            # open left the archive but stayed on the old tab without this.
            # test_clicking_the_other_tab_leaves_the_archive_for_that_tab.
            self.tabs.setCurrentIndex(index)

    def create_project(self) -> None:
        dialog = CreateProjectDialog(self.store, self)
        if dialog.exec():
            # New work is live work: show it where it landed.
            self.show_archive(False)
            self.tabs.setCurrentWidget(self.projects_view)

    def create_task(self) -> None:
        if not self.store.projects():
            answer = QMessageBox.question(
                self,
                "No projects yet",
                "A task has to belong to a project, and there are none yet.\n\n"
                "Create a project now?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer == QMessageBox.Yes:
                self.create_project()
                if self.store.projects():
                    self.create_task()
            return

        dialog = CreateTaskDialog(self.store, self)
        if dialog.exec():
            self.show_archive(False)

    # -- chrome ---------------------------------------------------------

    def _refresh_status(self) -> None:
        projects, tasks, done = self.store.counts()
        archived = self.store.archived_count()
        if not projects and not tasks and not archived:
            self.counts_label.setText("")
            return
        noun_p = "project" if projects == 1 else "projects"
        noun_t = "task" if tasks == 1 else "tasks"
        text = f"{projects} {noun_p}   ·   {tasks} {noun_t}   ·   {done} done"
        if archived:
            text += f"   ·   {archived} archived"
        self.counts_label.setText(text)

    def show_error(self, message: str) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Storage problem")
        box.setText(message)
        box.exec()

    def notify(self, title: str, message: str) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle(title)
        box.setText(message)
        box.exec()


def _display_path(path: Path) -> str:
    """The path with the home folder written as ~, as a terminal would."""
    try:
        return "~/" + str(Path(path).resolve().relative_to(Path.home().resolve()))
    except ValueError:
        return str(path)
