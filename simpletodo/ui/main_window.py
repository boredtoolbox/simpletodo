"""The application window: a Notes-style browser and a quiet status bar."""

from __future__ import annotations

import warnings
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..store import TodoStore
from . import macos
from .dialogs import CreateProjectDialog, CreateTaskDialog, MessageDialog, confirm
from .style import SIDEBAR_GUTTER, SPACE_1, SPACE_2, SPACE_3, TOOL_SIZE
from .views import Browser, Mode
from .widgets import ElidedLabel, TopBar, rounded_menu

APP_TITLE = "Simple To Do"
ADD_BUTTON_SIZE = TOOL_SIZE
#: The top bar's height where the window keeps a native title bar (Linux).
#: On macOS it is the title bar's own height, read once the window is shown.
TOP_BAR_HEIGHT = 40
MIN_WIDTH = 600
MIN_HEIGHT = 440


class MainWindow(QMainWindow):
    def __init__(self, store: TodoStore) -> None:
        super().__init__()
        self.store = store

        self.setWindowTitle("SimpleTodo")
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)
        self.resize(860, 580)

        # As in Notes, the content runs up under a see-through title bar, so
        # the traffic lights sit inside the sidebar and the toolbar shares
        # their row. Elsewhere the native title bar stays.
        self._under_title_bar = QGuiApplication.platformName() == "cocoa"
        if self._under_title_bar:
            with warnings.catch_warnings():
                # PySide flags the value as deprecated because an old,
                # deprecated flag shares it; the new name is the right one.
                warnings.simplefilter("ignore", DeprecationWarning)
                self.setWindowFlag(Qt.ExpandedClientAreaHint, True)
                self.setWindowFlag(Qt.NoTitleBarBackgroundHint, True)
            # Qt otherwise insets the contents by the title bar's height,
            # undoing the point of running under it.
            self.setAttribute(Qt.WA_ContentsMarginsRespectsSafeArea, False)

        # -- the sidebar header: masthead, +, and the view switch --------

        self.title_label = QLabel(APP_TITLE)
        self.title_label.setObjectName("appTitle")

        self.add_button = QPushButton("+")
        self.add_button.setObjectName("addButton")
        self.add_button.setFixedSize(ADD_BUTTON_SIZE, ADD_BUTTON_SIZE)
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.setToolTip("Create a project or a task")
        self.add_button.clicked.connect(self._show_add_menu)

        # The sidebar's share of the top bar: the traffic lights on the left
        # (on macOS), the + on the right, the window draggable in between.
        self.sidebar_bar = TopBar()
        bar = QHBoxLayout(self.sidebar_bar)
        bar.setContentsMargins(0, 0, SIDEBAR_GUTTER + SPACE_1, 0)
        bar.addStretch(1)
        bar.addWidget(self.add_button)

        # Archive sits in the switch beside Projects and Date, so the way back
        # out of it is always on screen. A lone toggle button was not: people
        # could not find their way back from the archive.
        segment_bar = QWidget()
        segment_bar.setObjectName("segmentBar")
        segment_bar.setAttribute(Qt.WA_StyledBackground, True)
        segments = QHBoxLayout(segment_bar)
        segments.setContentsMargins(2, 2, 2, 2)
        segments.setSpacing(2)
        self.segment_group = QButtonGroup(self)
        self.segments: dict[Mode, QPushButton] = {}
        for mode in Mode:
            button = QPushButton(mode.value)
            button.setObjectName("segment")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setFocusPolicy(Qt.NoFocus)
            button.clicked.connect(lambda _=False, m=mode: self.show_mode(m))
            self.segment_group.addButton(button)
            self.segments[mode] = button
            segments.addWidget(button, 1)

        header = QWidget()
        header.setObjectName("sidebarHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, SPACE_3)
        header_layout.setSpacing(0)
        header_layout.addWidget(self.sidebar_bar)
        # Text in the header lines up with the text of the items below.
        inset = SIDEBAR_GUTTER + SPACE_2
        below = QVBoxLayout()
        below.setContentsMargins(inset, SPACE_2, inset, 0)
        below.setSpacing(SPACE_3)
        below.addWidget(self.title_label)
        below.addWidget(segment_bar)
        header_layout.addLayout(below)

        self.browser = Browser(store, header)
        self.browser.newTaskRequested.connect(self.create_task)
        self.setCentralWidget(self.browser)
        self._set_top_bar_height(TOP_BAR_HEIGHT)

        leave = QShortcut(QKeySequence(Qt.Key_Escape), self)
        leave.activated.connect(lambda: self.show_archive(False))
        self._last_live_mode = Mode.PROJECTS

        # -- status bar ---------------------------------------------------

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

        self.show_mode(Mode.PROJECTS)
        store.changed.connect(self._refresh_status)
        store.taskCompleted.connect(self._refresh_status)
        store.errorOccurred.connect(self.show_error)
        self._refresh_status()

    # -- views ------------------------------------------------------------

    @property
    def mode(self) -> Mode:
        return self.browser.mode

    def show_mode(self, mode: Mode) -> None:
        if mode is not Mode.ARCHIVE:
            self._last_live_mode = mode
        self.segments[mode].setChecked(True)
        self.browser.set_mode(mode)

    def show_archive(self, shown: bool) -> None:
        """Open the archive, or go back to the view it was opened from."""
        self.show_mode(Mode.ARCHIVE if shown else self._last_live_mode)

    # -- the + menu -------------------------------------------------------

    def _show_add_menu(self) -> None:
        menu = rounded_menu(self)
        new_project = QAction("Create Project", self)
        new_project.triggered.connect(self.create_project)
        new_task = QAction("Create Task", self)
        new_task.triggered.connect(lambda: self.create_task())
        menu.addAction(new_project)
        menu.addAction(new_task)

        anchor = self.add_button.mapToGlobal(QPoint(0, self.add_button.height()))
        menu.popup(anchor + QPoint(0, SPACE_1))

    def create_project(self) -> None:
        dialog = CreateProjectDialog(self.store, self)
        # New work is live work: show it where it landed.
        dialog.created.connect(lambda project: self._reveal_project(project.id))
        dialog.exec()

    def create_task(self, project_id: int | None = None) -> None:
        """Ask for a new task, filed under *project_id* unless changed."""
        if not self.store.projects():
            if confirm(
                self,
                "No Projects Yet",
                "A task has to belong to a project, and there are none yet. "
                "Create a project now?",
                confirm_text="New Project",
            ):
                self.create_project()
                if self.store.projects():
                    self.create_task()
            return

        dialog = CreateTaskDialog(self.store, self, preselect_project_id=project_id)
        dialog.created.connect(self._reveal_task)
        dialog.exec()

    def _reveal_task(self, task) -> None:
        # In the Date view the task already shows under its bucket; anywhere
        # else, open its project so it is seen.
        if self.mode is not Mode.DATE:
            self._reveal_project(task.project_id)

    def _reveal_project(self, project_id: int) -> None:
        self._last_live_mode = Mode.PROJECTS
        self.segments[Mode.PROJECTS].setChecked(True)
        self.browser.reveal_project(project_id)

    # -- chrome -----------------------------------------------------------

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
        MessageDialog("Storage Problem", message, self, cancel_text=None).exec()

    def notify(self, title: str, message: str) -> None:
        MessageDialog(title, message, self, cancel_text=None).exec()

    # -- the top bar -------------------------------------------------------

    def showEvent(self, event):  # noqa: N802 - Qt naming
        super().showEvent(event)
        if self._under_title_bar:
            macos.hide_title_text(self)
            # The traffic lights are centred in the title bar, so a top bar
            # exactly as tall puts the + and the toolbar on their line.
            title_bar = self.windowHandle().safeAreaMargins().top()
            if title_bar > 0:
                self._set_top_bar_height(title_bar)

    def _set_top_bar_height(self, height: int) -> None:
        self.sidebar_bar.setFixedHeight(height)
        self.browser.top_bar.setFixedHeight(height)


def _display_path(path: Path) -> str:
    """The path with the home folder written as ~, as a terminal would."""
    try:
        return "~/" + str(Path(path).resolve().relative_to(Path.home().resolve()))
    except ValueError:
        return str(path)
