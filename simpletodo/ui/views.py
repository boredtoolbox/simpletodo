"""The Projects tab and the Date tab.

Both observe the store and rebuild themselves whenever it reports a change,
remembering which sections the person had opened.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from ..dates import Bucket
from ..models import Project, Task
from ..store import TodoStore
from .style import CONTENT_WIDTH, SECTION_GAP, SPACE_4, SPACE_6
from .dialogs import RenameDialog
from .widgets import CollapsibleSection, TaskRow, rounded_menu

#: The Date tab lists completed work greyed out rather than hiding it, so that
#: a section's (X/Y) count means something and ticking a box is not a vanishing
#: act. Flip this to True to show only outstanding tasks there.
HIDE_COMPLETED_IN_DATE_VIEW = False


class _CentredScrollView(QWidget):
    """A scrollable column of sections, centred in both directions.

    The content sits in the middle of the window while it fits, and anchors to
    the top and scrolls once it does not. Both behaviours come from elastic
    spacers, so the list re-centres itself whenever the window is resized,
    maximised, or a section is expanded -- no resize handler needed.
    """

    def __init__(self, store: TodoStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("tabPage")
        self.store = store

        self.column = QWidget()
        self.column.setObjectName("contentColumn")
        self.column.setMaximumWidth(CONTENT_WIDTH)
        self.column_layout = QVBoxLayout(self.column)
        self.column_layout.setContentsMargins(0, 0, 0, 0)
        self.column_layout.setSpacing(SECTION_GAP)
        self.column_layout.setAlignment(Qt.AlignTop)

        # Horizontal centring uses two elastic margins rather than an alignment
        # flag: a flag would pin the column to its size hint, and the hint goes
        # stale the moment a section is expanded.
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addStretch(1)
        row.addWidget(self.column, 100)
        row.addStretch(1)

        # Vertical centring works the same way. The spacers absorb the slack
        # when the list is short and collapse to nothing when it is long, so
        # a tall list still starts at the top and scrolls normally.
        self.top_spacer = QSpacerItem(
            0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding
        )
        self.bottom_spacer = QSpacerItem(
            0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding
        )

        centred = QWidget()
        centred.setObjectName("scrollHolder")
        centring = QVBoxLayout(centred)
        centring.setContentsMargins(SPACE_6, SPACE_4, SPACE_6, SPACE_6)
        centring.setSpacing(0)
        centring.addItem(self.top_spacer)
        centring.addLayout(row)
        centring.addItem(self.bottom_spacer)
        # A hair above true centre reads better than dead centre.
        centring.setStretch(0, 4)
        centring.setStretch(2, 5)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(centred)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # The viewport fills itself with the palette colour by default, which
        # would hide the paper grain painted on the backdrop behind it.
        self.scroll.viewport().setAutoFillBackground(False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.scroll)

    def _settle(self) -> None:
        """Re-fit the scrolled widget after the column's contents changed.

        QScrollArea only shrinks its widget when the layout is re-activated.
        Without this the holder keeps the height of the longest list it has
        ever shown, and a now-short list is pushed below the fold instead of
        re-centring.
        """
        holder = self.scroll.widget()
        if holder is None:
            return

        # Size hints are computed bottom-up, and a layout ignores a widget that
        # is not yet visible. Qt only shows freshly added children on the next
        # event-loop turn, so show them now and activate their layouts -- without
        # this the holder measures an empty list and the column stays squashed.
        for index in range(self.column_layout.count()):
            widget = self.column_layout.itemAt(index).widget()
            if widget is None:
                continue
            widget.setVisible(True)
            if widget.layout() is not None:
                widget.layout().activate()
        self.column_layout.invalidate()
        self.column_layout.activate()
        self.column.updateGeometry()

        layout = holder.layout()
        if layout is None:
            return
        layout.invalidate()
        layout.activate()

        # Apply the fit now instead of waiting for the scroll area's deferred
        # LayoutRequest. Without this the geometry trails a frame behind, and
        # a burst of changes can leave the list squashed into one viewport.
        viewport = self.scroll.viewport()
        wanted = max(viewport.height(), holder.sizeHint().height())
        if holder.height() != wanted:
            holder.resize(viewport.width(), wanted)

    def _clear_column(self) -> None:
        while self.column_layout.count():
            item = self.column_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _placeholder(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("bigEmpty")
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        return label

    def _empty_note(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("emptyNote")
        label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        return label

    def _wire_row(self, row: TaskRow) -> None:
        row.toggled.connect(self.store.set_task_completed)
        row.menuRequested.connect(
            lambda position, task=row.task: self._task_menu(task, position)
        )
        # Revealing a description makes the row taller; re-fit around it.
        row.descriptionToggled.connect(lambda _: self._settle())

    # -- task actions ---------------------------------------------------

    def _task_menu(self, task: Task, position: QPoint) -> QMenu:
        """Open the task menu. Non-blocking, like every other menu here."""
        menu = rounded_menu(self)
        menu.setAttribute(Qt.WA_DeleteOnClose)
        menu.addAction("Rename\u2026").triggered.connect(
            lambda: self._rename_task(task)
        )
        menu.addAction("Delete task").triggered.connect(
            lambda: self._delete_task(task)
        )
        menu.popup(position)
        return menu

    def _rename_task(self, task: Task) -> None:
        dialog = RenameDialog(
            self.store,
            title="Rename Task",
            field_label="Task name",
            current_name=task.name,
            parent=self,
        )
        if dialog.exec() and dialog.new_name and task.id is not None:
            self.store.rename_task(task.id, dialog.new_name)

    def _delete_task(self, task: Task) -> None:
        answer = QMessageBox.question(
            self,
            "Delete task",
            f"Delete \u201c{task.name}\u201d?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes and task.id is not None:
            self.store.delete_task(task.id)


class ProjectsView(_CentredScrollView):
    """Every project, expandable to reveal its tasks.

    With *archived* set it lists the archived projects instead -- the same
    page, offering Restore where the live list offers Archive.
    """

    def __init__(
        self,
        store: TodoStore,
        parent: QWidget | None = None,
        *,
        archived: bool = False,
    ) -> None:
        super().__init__(store, parent)
        self.archived = archived
        self._open_ids: set[int] = set()
        self.store.projectsChanged.connect(self.refresh)
        self.store.tasksChanged.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        self._clear_column()
        projects = self.store.projects(archived=self.archived)

        if not projects:
            if self.archived:
                empty = "Nothing archived.\n\nArchive a project from its \u22ef menu."
            else:
                empty = "No projects yet.\n\nUse the + button to create one."
            self.column_layout.addWidget(self._placeholder(empty))
            self._settle()
            return

        for project in projects:
            section = CollapsibleSection(project.name, with_menu=True)
            section.menuRequested.connect(
                lambda position, p=project: self._project_menu(p, position)
            )
            section.set_counts(project.completed_tasks, project.total_tasks)

            tasks = self.store.tasks_for_project(project.id)
            if tasks:
                for task in tasks:
                    row = TaskRow(task, show_project=False)
                    self._wire_row(row)
                    section.add_row(row)
            else:
                section.add_row(self._empty_note("no tasks"))

            project_id = project.id
            section.toggled.connect(
                lambda opened, pid=project_id: self._remember(pid, opened)
            )
            section.toggled.connect(lambda _: self._settle())
            self.column_layout.addWidget(section)

            if project_id in self._open_ids:
                section.set_expanded(True, animate=False)

        self._settle()

    def _remember(self, project_id: int, opened: bool) -> None:
        if opened:
            self._open_ids.add(project_id)
        else:
            self._open_ids.discard(project_id)

    # -- project actions ------------------------------------------------

    def _project_menu(self, project: Project, position: QPoint) -> QMenu:
        menu = rounded_menu(self)
        menu.setAttribute(Qt.WA_DeleteOnClose)
        menu.addAction("Rename\u2026").triggered.connect(
            lambda: self._rename_project(project)
        )
        if self.archived:
            menu.addAction("Restore project").triggered.connect(
                lambda: self.store.set_project_archived(project.id, False)
            )
        else:
            menu.addAction("Archive project").triggered.connect(
                lambda: self.store.set_project_archived(project.id, True)
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
            field_label="Project name",
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
        answer = QMessageBox.question(
            self,
            "Delete project",
            f"Delete \u201c{project.name}\u201d?\n\n{detail}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes and project.id is not None:
            self.store.delete_project(project.id)


class DateView(_CentredScrollView):
    """Today, Tomorrow, This Week and Rest."""

    def __init__(self, store: TodoStore, parent: QWidget | None = None) -> None:
        super().__init__(store, parent)
        # Today is the section people want on arrival.
        self._open_buckets: set[Bucket] = {Bucket.TODAY}
        self.store.tasksChanged.connect(self.refresh)
        self.store.projectsChanged.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        self._clear_column()
        any_tasks = False

        for bucket in Bucket:
            tasks = self.store.tasks_in_bucket(
                bucket, include_completed=not HIDE_COMPLETED_IN_DATE_VIEW
            )
            any_tasks = any_tasks or bool(tasks)

            section = CollapsibleSection(bucket.label)
            section.set_counts(sum(t.is_completed for t in tasks), len(tasks))

            if tasks:
                for task in tasks:
                    row = TaskRow(task, show_project=True)
                    self._wire_row(row)
                    section.add_row(row)
            else:
                section.add_row(self._empty_note("nothing here"))

            section.toggled.connect(
                lambda opened, b=bucket: self._remember(b, opened)
            )
            section.toggled.connect(lambda _: self._settle())
            self.column_layout.addWidget(section)

            if bucket in self._open_buckets:
                section.set_expanded(True, animate=False)

        if not any_tasks:
            self.column_layout.addWidget(
                self._placeholder("Nothing scheduled.\n\nUse the + button to add a task.")
            )

        self._settle()

    def _remember(self, bucket: Bucket, opened: bool) -> None:
        if opened:
            self._open_buckets.add(bucket)
        else:
            self._open_buckets.discard(bucket)
