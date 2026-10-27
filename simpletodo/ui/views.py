"""The sidebar and the task pane, and the Browser that binds them to the store.

The window is laid out like Apple Notes: a list on the left -- projects, the
four date buckets, or the archive, depending on the switch above it -- and on
the right the tasks of whichever entry is selected. Above the projects sit
two shelves, Pinned and Inbox, each listed only while it holds a task.

The Browser observes the store and rebuilds both halves whenever it reports a
change, remembering the selection in each mode. Ticking a box is the
exception: it updates the existing rows and counts, since nothing appears or
disappears.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from ..dates import Bucket
from ..models import Project, Task
from ..store import TodoStore
from .dialogs import RenameDialog, confirm
from .style import (
    SEARCH_WIDTH,
    SIDEBAR_GUTTER,
    SIDEBAR_WIDTH,
    SPACE_1,
    SPACE_2,
    SPACE_3,
    SPACE_6,
    SPACE_8,
    TOOL_SIZE,
    icon_svg,
)
from .widgets import (
    SidebarItem,
    TaskRow,
    TopBar,
    restyle,
    rounded_menu,
    settle_scroll,
    svg_icon,
)

#: The Date view lists completed work greyed out rather than hiding it, so that
#: a bucket's X/Y count means something and ticking a box is not a vanishing
#: act. Flip this to True to show only outstanding tasks there.
HIDE_COMPLETED_IN_DATE_VIEW = False


class Mode(Enum):
    """What the sidebar lists. The value is the switch's label."""

    PROJECTS = "Projects"
    DATE = "Date"
    ARCHIVE = "Archive"


class Shelf(Enum):
    """Projects-view entries that are not projects. The value is the title."""

    #: Pinned tasks from everywhere. First in the list, so it is what the
    #: window opens on whenever something is pinned.
    PINNED = "Pinned"
    #: Tasks that belong to no project.
    INBOX = "Inbox"


@dataclass
class Entry:
    """One sidebar line: a project (keyed by id), a Shelf or a date bucket."""

    key: object
    title: str
    done: int
    total: int
    #: The next task still to do, shown muted after the count.
    preview: str
    #: Whether it has a ⋯ menu; only projects do.
    has_menu: bool = False


def _discard(widget: QWidget | None) -> None:
    """Remove a widget taken out of a layout.

    Hidden and deleted, never detached first: setParent(None) turns it into a
    top-level window until the deletion lands, and after a couple of rebuilds
    the main window could no longer be activated, so its Esc shortcut went
    dead. See test_escape_leaves_the_archive_for_the_view_it_came_from.
    """
    if widget is not None:
        widget.hide()
        widget.deleteLater()


# -- the sidebar --------------------------------------------------------


class Sidebar(QWidget):
    """A scrolling list of SidebarItems with one selected.

    Up and Down move the selection, as in Notes.
    """

    #: The person picked an entry, by click or arrow key.
    chosen = Signal(object)
    #: An entry's menu was asked for: its key and a global position.
    menuRequested = Signal(object, QPoint)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.items: list[SidebarItem] = []
        self._dividers: list[QFrame] = []
        self._selected_key: object = None

        self.list = QWidget()
        self.list.setObjectName("sidebarList")
        self._layout = QVBoxLayout(self.list)
        self._layout.setContentsMargins(SIDEBAR_GUTTER, 0, SIDEBAR_GUTTER, SPACE_2)
        self._layout.setSpacing(0)
        self._layout.addStretch(1)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.list)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # The arrow keys belong to the list, not to the scroll area.
        self.scroll.setFocusPolicy(Qt.NoFocus)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.scroll)

    @property
    def selected_key(self) -> object:
        return self._selected_key

    def set_entries(self, entries: list[Entry], *, with_menu: bool) -> None:
        while self._layout.count() > 1:          # keep the trailing stretch
            _discard(self._layout.takeAt(0).widget())
        self.items, self._dividers = [], []
        self._selected_key = None

        for index, entry in enumerate(entries):
            if index:
                divider = QFrame()
                divider.setObjectName("sidebarDivider")
                divider.setFixedHeight(1)
                self._dividers.append(divider)
                self._layout.insertWidget(self._layout.count() - 1, divider)
            item = SidebarItem(
                entry.key, entry.title, with_menu=with_menu and entry.has_menu
            )
            item.chosen.connect(self._on_item_chosen)
            item.menuRequested.connect(
                lambda position, key=entry.key: self.menuRequested.emit(key, position)
            )
            self.items.append(item)
            self._layout.insertWidget(self._layout.count() - 1, item)
        self.update_entries(entries)
        settle_scroll(self.scroll)

    def update_entries(self, entries: list[Entry]) -> None:
        """Rewrite the counts and previews of the items already shown."""
        by_key = {item.key: item for item in self.items}
        for entry in entries:
            item = by_key.get(entry.key)
            if item is not None:
                item.set_detail(f"{entry.done}/{entry.total}", entry.preview)

    def select(self, key: object) -> None:
        self._selected_key = key
        for item in self.items:
            item.set_selected(item.key == key)
        # Notes drops the hairline on either side of the selection; the slab
        # is its own boundary. The divider keeps its height so nothing moves.
        for index, divider in enumerate(self._dividers):
            above, below = self.items[index], self.items[index + 1]
            divider.setProperty("clear", above.selected or below.selected)
            restyle(divider)
        current = self._item(key)
        if current is not None:
            self.scroll.ensureWidgetVisible(current, 0, SPACE_2)

    def _item(self, key: object) -> SidebarItem | None:
        return next((item for item in self.items if item.key == key), None)

    def _on_item_chosen(self, key: object) -> None:
        self.setFocus(Qt.MouseFocusReason)
        self.chosen.emit(key)

    def keyPressEvent(self, event):  # noqa: N802 - Qt naming
        step = {Qt.Key_Up: -1, Qt.Key_Down: 1}.get(event.key())
        keys = [item.key for item in self.items]
        if step is None or not keys:
            super().keyPressEvent(event)
            return
        index = keys.index(self._selected_key) if self._selected_key in keys else -1
        target = min(max(index + step, 0), len(keys) - 1)
        if keys[target] != self._selected_key:
            self.chosen.emit(keys[target])
        event.accept()


# -- the task pane ------------------------------------------------------


class TaskPane(QWidget):
    """The selected entry's heading and its tasks, or a centred message."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title_label = QLabel("")
        self.title_label.setObjectName("paneTitle")
        self.title_label.setWordWrap(True)
        self.subtitle_label = QLabel("")
        self.subtitle_label.setObjectName("paneSubtitle")

        self.column = QWidget()
        self.column.setObjectName("paneColumn")
        self._layout = QVBoxLayout(self.column)
        self._layout.setContentsMargins(SPACE_8, SPACE_6, SPACE_8, SPACE_6)
        self._layout.setSpacing(SPACE_1)
        self._layout.addWidget(self.title_label)
        self._layout.addWidget(self.subtitle_label)
        self._layout.addSpacing(SPACE_6 - SPACE_1)
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        self._layout.addLayout(self._rows_layout)
        self._layout.addStretch(1)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.column)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.message = QLabel("")
        self.message.setObjectName("bigEmpty")
        self.message.setAlignment(Qt.AlignCenter)
        self.message.setWordWrap(True)

        self._filter = ""
        self._no_match: QLabel | None = None

        self._stack = QStackedLayout(self)
        self._stack.addWidget(self.scroll)
        self._stack.addWidget(self.message)

    @property
    def rows(self) -> list[TaskRow]:
        return [
            self._rows_layout.itemAt(i).widget()
            for i in range(self._rows_layout.count())
            if isinstance(self._rows_layout.itemAt(i).widget(), TaskRow)
        ]

    def show_tasks(
        self,
        title: str,
        subtitle: str,
        tasks: list[Task],
        *,
        show_project: bool,
        show_date: bool,
        empty_note: str,
    ) -> list[TaskRow]:
        self._clear_rows()
        self.title_label.setText(title)
        self.subtitle_label.setText(subtitle)
        rows = [
            TaskRow(task, show_project=show_project, show_date=show_date)
            for task in tasks
        ]
        for row in rows:
            self._rows_layout.addWidget(row)
        if not rows:
            note = QLabel(empty_note)
            note.setObjectName("emptyNote")
            self._rows_layout.addWidget(note)
        self._no_match = QLabel("No matching tasks.")
        self._no_match.setObjectName("emptyNote")
        self._rows_layout.addWidget(self._no_match)
        self._apply_filter()
        self._stack.setCurrentWidget(self.scroll)
        settle_scroll(self.scroll)
        self.scroll.verticalScrollBar().setValue(0)
        return rows

    def show_message(self, text: str) -> None:
        self._clear_rows()
        self._no_match = None
        self.message.setText(text)
        self._stack.setCurrentWidget(self.message)

    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.setText(text)

    def set_filter(self, text: str) -> None:
        """Show only the tasks whose name or description contains *text*."""
        self._filter = text.strip().casefold()
        self._apply_filter()

    def _apply_filter(self) -> None:
        rows = self.rows
        shown = 0
        for row in rows:
            haystack = f"{row.task.name}\n{row.task.description}".casefold()
            match = self._filter in haystack
            row.setVisible(match)
            shown += match
        if self._no_match is not None:
            self._no_match.setVisible(bool(rows) and not shown)
        settle_scroll(self.scroll)

    def _clear_rows(self) -> None:
        while self._rows_layout.count():
            _discard(self._rows_layout.takeAt(0).widget())


# -- the browser --------------------------------------------------------


def _tool_button(icon: str, tip: str) -> QPushButton:
    """A round top-bar button, as Notes draws them."""
    button = QPushButton()
    button.setObjectName("toolButton")
    button.setFixedSize(TOOL_SIZE + 6, TOOL_SIZE)
    button.setIcon(svg_icon(icon_svg(icon), 18))
    button.setIconSize(QSize(18, 18))
    button.setToolTip(tip)
    button.setFocusPolicy(Qt.NoFocus)
    _float(button)
    return button


def _float(widget: QWidget) -> None:
    """The soft shadow that lifts Notes' toolbar pills off the page."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(10)
    shadow.setOffset(0, 1)
    shadow.setColor(QColor(0, 0, 0, 28))
    widget.setGraphicsEffect(shadow)


class Browser(QWidget):
    """Sidebar on the left, the selected entry's tasks on the right.

    *header* is placed above the sidebar list, inside the sidebar column, so
    the window's title and switch line up with the list beneath them. Over
    the pane runs a top bar: new task, the selected project's menu, search.
    """

    #: The top bar's new-task button: the selected project id, or None.
    newTaskRequested = Signal(object)

    #: Shown in the pane when the sidebar has nothing to select.
    EMPTY = {
        Mode.PROJECTS: (
            "No projects yet.\n\n"
            "Use the + button to create one, or to add a task on its own."
        ),
        Mode.ARCHIVE: "Nothing archived.\n\nArchive a project from its ⋯ menu.",
    }

    def __init__(
        self, store: TodoStore, header: QWidget, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.mode = Mode.PROJECTS
        # Today is what people want on arrival in the Date view.
        self._chosen: dict[Mode, object] = {Mode.DATE: Bucket.TODAY}
        self._projects: dict[int, Project] = {}

        self.sidebar = Sidebar()
        self.sidebar.chosen.connect(self.select)
        self.sidebar.menuRequested.connect(
            lambda key, position: self._project_menu(self._projects[key], position)
        )
        self.pane = TaskPane()

        self.compose_button = _tool_button("compose", "New task")
        self.compose_button.clicked.connect(
            lambda: self.newTaskRequested.emit(self.selected_project_id)
        )
        self.more_button = _tool_button("more", "Project actions")
        self.more_button.clicked.connect(self._show_more_menu)

        self.search_field = QLineEdit()
        self.search_field.setObjectName("searchField")
        self.search_field.setPlaceholderText("Search")
        self.search_field.setClearButtonEnabled(True)
        self.search_field.setFixedWidth(SEARCH_WIDTH)
        self.search_field.addAction(
            svg_icon(icon_svg("search"), 16), QLineEdit.LeadingPosition
        )
        self.search_field.textChanged.connect(self.pane.set_filter)
        _float(self.search_field)

        self.top_bar = TopBar()
        bar = QHBoxLayout(self.top_bar)
        bar.setContentsMargins(SPACE_3, 0, SPACE_3, 0)
        bar.setSpacing(SPACE_2)
        bar.addWidget(self.compose_button)
        bar.addWidget(self.more_button)
        bar.addStretch(1)
        bar.addWidget(self.search_field)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self.top_bar)
        right_layout.addWidget(self.pane, 1)

        column = QWidget()
        column.setObjectName("sidebarColumn")
        column.setFixedWidth(SIDEBAR_WIDTH)
        # Paints its own background, so the border-right divider shows.
        column.setAttribute(Qt.WA_StyledBackground, True)
        side = QVBoxLayout(column)
        side.setContentsMargins(0, 0, 1, 0)       # leave the 1px border visible
        side.setSpacing(0)
        side.addWidget(header)
        side.addWidget(self.sidebar, 1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(column)
        layout.addWidget(right, 1)

        store.changed.connect(self.refresh)
        store.taskCompleted.connect(self._on_task_completed)
        self.refresh()

    # -- what is shown --------------------------------------------------

    def set_mode(self, mode: Mode) -> None:
        if mode is self.mode:
            return
        self.mode = mode
        self.refresh()

    def refresh(self) -> None:
        entries = self._entries()
        self.sidebar.set_entries(entries, with_menu=self.mode is not Mode.DATE)
        keys = [entry.key for entry in entries]
        key = self._chosen.get(self.mode)
        if key not in keys:
            key = keys[0] if keys else None
        self.select(key)

    @property
    def selected_project_id(self) -> int | None:
        key = self._chosen.get(self.mode)
        return key if self.mode is not Mode.DATE and key in self._projects else None

    def _show_more_menu(self) -> None:
        project = self._projects.get(self.selected_project_id)
        if project is not None:
            corner = self.more_button.mapToGlobal(QPoint(0, self.more_button.height()))
            self._project_menu(project, corner + QPoint(0, SPACE_1))

    def select(self, key: object) -> None:
        """Show *key*'s tasks: a project id, or a Bucket in the Date view."""
        self._chosen[self.mode] = key
        self.sidebar.select(key)
        # The project menu only means something with a project in view.
        self.more_button.setEnabled(self.selected_project_id is not None)
        if key is None:
            self.pane.show_message(self.EMPTY.get(self.mode, ""))
            return

        tasks = self._tasks_for(key)
        done = sum(task.is_completed for task in tasks)
        if isinstance(key, Bucket):
            title, empty = key.label, "Nothing due."
        elif isinstance(key, Shelf):
            title, empty = key.value, "Nothing here."
        else:
            title, empty = self._projects[key].name, "No tasks yet."
        subtitle = f"{done} of {len(tasks)} done" if tasks else ""
        if self.mode is Mode.ARCHIVE:
            subtitle = " · ".join(p for p in ("Archived", subtitle) if p)

        # Pinned gathers tasks from every project, so it names theirs; a
        # bucket's title is already their date.
        rows = self.pane.show_tasks(
            title, subtitle, tasks,
            show_project=self.mode is Mode.DATE or key is Shelf.PINNED,
            show_date=self.mode is not Mode.DATE,
            empty_note=empty,
        )
        for row in rows:
            self._wire_row(row)

    def reveal(self, key: int | Shelf) -> None:
        """Switch to the Projects view with a project or a shelf selected."""
        self._chosen[Mode.PROJECTS] = key
        if self.mode is Mode.PROJECTS:
            self.select(key)
        else:
            self.set_mode(Mode.PROJECTS)

    def _entries(self) -> list[Entry]:
        if self.mode is Mode.DATE:
            return [
                self._entry(bucket, bucket.label, self._tasks_for(bucket))
                for bucket in Bucket
            ]
        entries = []
        if self.mode is Mode.PROJECTS:
            # An empty shelf is clutter; it appears with its first task.
            for shelf in Shelf:
                tasks = self._tasks_for(shelf)
                if tasks:
                    entries.append(self._entry(shelf, shelf.value, tasks))
        projects = self.store.projects(archived=self.mode is Mode.ARCHIVE)
        self._projects = {project.id: project for project in projects}
        entries += [
            self._entry(
                project.id, project.name, self._tasks_for(project.id),
                has_menu=True,
            )
            for project in projects
        ]
        return entries

    @staticmethod
    def _entry(
        key: object, title: str, tasks: list[Task], *, has_menu: bool = False
    ) -> Entry:
        done = sum(task.is_completed for task in tasks)
        upcoming = next((task.name for task in tasks if not task.is_completed), None)
        if upcoming is None:
            upcoming = "All done" if tasks else "No tasks"
        return Entry(key, title, done, len(tasks), upcoming, has_menu)

    def _tasks_for(self, key: object) -> list[Task]:
        if isinstance(key, Bucket):
            return self.store.tasks_in_bucket(
                key, include_completed=not HIDE_COMPLETED_IN_DATE_VIEW
            )
        if key is Shelf.PINNED:
            return self.store.pinned_tasks()
        if key is Shelf.INBOX:
            return self.store.loose_tasks()
        return self.store.tasks_for_project(key)

    def _on_task_completed(self, task_id: int, done: bool) -> None:
        """Mark the task's rows done and recount, in place.

        A rebuild here destroyed the very checkbox being clicked and took
        about a second on macOS before the tick could be drawn.
        """
        if self.mode is Mode.DATE and HIDE_COMPLETED_IN_DATE_VIEW:
            # The row has to leave or arrive, which only a rebuild does.
            self.refresh()
            return
        rows = self.pane.rows
        for row in rows:
            if row.task.id == task_id:
                row.set_completed(done)
        if rows:
            finished = sum(row.task.is_completed for row in rows)
            subtitle = f"{finished} of {len(rows)} done"
            if self.mode is Mode.ARCHIVE:
                subtitle = f"Archived · {subtitle}"
            self.pane.set_subtitle(subtitle)
        self.sidebar.update_entries(self._entries())

    def _wire_row(self, row: TaskRow) -> None:
        row.toggled.connect(self.store.set_task_completed)
        row.menuRequested.connect(
            lambda position, task=row.task: self._task_menu(task, position)
        )

    # -- task actions ---------------------------------------------------

    def _task_menu(self, task: Task, position: QPoint) -> QMenu:
        """Open the task menu. Non-blocking, like every other menu here."""
        menu = rounded_menu(self)
        menu.setAttribute(Qt.WA_DeleteOnClose)
        menu.addAction("Unpin" if task.is_pinned else "Pin").triggered.connect(
            lambda: self.store.set_task_pinned(task.id, not task.is_pinned)
        )
        menu.addAction("Rename…").triggered.connect(
            lambda: self._rename_task(task)
        )
        menu.addMenu(self._move_menu(task, menu))
        menu.addAction("Delete task").triggered.connect(
            lambda: self._delete_task(task)
        )
        menu.popup(position)
        return menu

    def _move_menu(self, task: Task, parent: QMenu) -> QMenu:
        """Every other live project, and the Inbox, as places to send *task*."""
        move = rounded_menu(parent)
        move.setTitle("Move to")
        targets = [(p.id, p.name) for p in self.store.projects()]
        targets.insert(0, (None, Shelf.INBOX.value))
        targets = [t for t in targets if t[0] != task.project_id]
        for project_id, name in targets:
            move.addAction(name).triggered.connect(
                lambda _=False, pid=project_id: self.store.move_task(task.id, pid)
            )
        move.setEnabled(bool(targets))
        return move

    def _rename_task(self, task: Task) -> None:
        dialog = RenameDialog(
            self.store,
            title="Rename Task",
            field_label="Name",
            current_name=task.name,
            parent=self,
        )
        if dialog.exec() and dialog.new_name and task.id is not None:
            self.store.rename_task(task.id, dialog.new_name)

    def _delete_task(self, task: Task) -> None:
        if confirm(
            self,
            "Delete Task",
            f"Delete “{task.name}”?",
            confirm_text="Delete",
            destructive=True,
        ) and task.id is not None:
            self.store.delete_task(task.id)

    # -- project actions ------------------------------------------------

    def _project_menu(self, project: Project, position: QPoint) -> QMenu:
        menu = rounded_menu(self)
        menu.setAttribute(Qt.WA_DeleteOnClose)
        menu.addAction("Rename…").triggered.connect(
            lambda: self._rename_project(project)
        )
        if project.is_active:
            menu.addAction("Archive project").triggered.connect(
                lambda: self.store.set_project_archived(project.id, True)
            )
        else:
            menu.addAction("Restore project").triggered.connect(
                lambda: self.store.set_project_archived(project.id, False)
            )
        menu.addAction("Delete project").triggered.connect(
            lambda: self._delete_project(project)
        )
        menu.popup(position)
        return menu

    def _rename_project(self, project: Project) -> None:
        dialog = RenameDialog(
            self.store,
            title="Rename Project",
            field_label="Name",
            current_name=project.name,
            taken=lambda name: self.store.project_exists(name, project.id),
            parent=self,
        )
        if dialog.exec() and dialog.new_name and project.id is not None:
            self.store.rename_project(project.id, dialog.new_name)

    def _delete_project(self, project: Project) -> None:
        count = project.total_tasks
        if count:
            detail = (
                f"Its {count} task{'s' if count != 1 else ''} will be "
                "deleted as well."
            )
        else:
            detail = "It has no tasks."
        if confirm(
            self,
            "Delete Project",
            f"Delete “{project.name}”? {detail}",
            confirm_text="Delete",
            destructive=True,
        ) and project.id is not None:
            self.store.delete_project(project.id)
