"""The observable middle layer.

Views never touch the Database directly. They call the store and listen to its
signals, so any change -- from any dialog or any view -- refreshes every other
view at once. This is the observer pattern, expressed with Qt signals.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .database import Database, DatabaseError
from .dates import Bucket
from .models import Project, Task


class TodoStore(QObject):
    """Single source of truth, and the only thing the views mutate."""

    #: The project list or any project's task counts changed.
    projectsChanged = Signal()
    #: Any task was added, removed, or toggled.
    tasksChanged = Signal()
    #: A storage problem the person should see.
    errorOccurred = Signal(str)

    def __init__(self, db: Database, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._db = db

    # -- reads ----------------------------------------------------------

    @property
    def database_path(self) -> Path:
        return self._db.path

    def projects(self, *, archived: bool = False) -> list[Project]:
        return self._guard(lambda: self._db.projects(archived=archived), default=[])

    def tasks_for_project(self, project_id: int) -> list[Task]:
        return self._guard(lambda: self._db.tasks_for_project(project_id), default=[])

    def tasks_in_bucket(
        self, bucket: Bucket, *, include_completed: bool = True
    ) -> list[Task]:
        return self._guard(
            lambda: self._db.tasks_in_bucket(
                bucket, date.today(), include_completed=include_completed
            ),
            default=[],
        )

    def counts(self) -> tuple[int, int, int]:
        return self._guard(self._db.counts, default=(0, 0, 0))

    def archived_count(self) -> int:
        return self._guard(self._db.archived_count, default=0)

    def project_exists(self, name: str, exclude_id: int | None = None) -> bool:
        return self._guard(
            lambda: self._db.project_exists(name, exclude_id), default=False
        )

    # -- writes ---------------------------------------------------------

    def create_project(self, name: str) -> Project | None:
        project = self._guard(lambda: self._db.add_project(name), default=None)
        if project is not None:
            self.projectsChanged.emit()
        return project

    def create_task(
        self, name: str, due_date: str, project_id: int, description: str = ""
    ) -> Task | None:
        task = self._guard(
            lambda: self._db.add_task(name, due_date, project_id, description),
            default=None,
        )
        if task is not None:
            self.tasksChanged.emit()
            self.projectsChanged.emit()   # the project's (X/Y) moved
        return task

    def rename_project(self, project_id: int, name: str) -> bool:
        ok = self._guard(
            lambda: (self._db.rename_project(project_id, name), True)[1], default=False
        )
        if ok:
            self.projectsChanged.emit()
            self.tasksChanged.emit()   # the Date tab prints project names
        return bool(ok)

    def rename_task(self, task_id: int, name: str) -> bool:
        ok = self._guard(
            lambda: (self._db.rename_task(task_id, name), True)[1], default=False
        )
        if ok:
            self.tasksChanged.emit()
        return bool(ok)

    def set_task_completed(self, task_id: int, completed: bool) -> bool:
        ok = self._guard(
            lambda: (self._db.set_task_completed(task_id, completed), True)[1],
            default=False,
        )
        if ok:
            self.tasksChanged.emit()
            self.projectsChanged.emit()
        return bool(ok)

    def delete_task(self, task_id: int) -> bool:
        ok = self._guard(
            lambda: (self._db.delete_task(task_id), True)[1], default=False
        )
        if ok:
            self.tasksChanged.emit()
            self.projectsChanged.emit()
        return bool(ok)

    def delete_project(self, project_id: int) -> bool:
        ok = self._guard(
            lambda: (self._db.delete_project(project_id), True)[1], default=False
        )
        if ok:
            self.projectsChanged.emit()
            self.tasksChanged.emit()
        return bool(ok)

    def set_project_archived(self, project_id: int, archived: bool) -> bool:
        ok = self._guard(
            lambda: (self._db.set_project_archived(project_id, archived), True)[1],
            default=False,
        )
        if ok:
            # The project's tasks leave (or rejoin) the Date tab too.
            self.projectsChanged.emit()
            self.tasksChanged.emit()
        return bool(ok)

    # -- plumbing -------------------------------------------------------

    def _guard(self, call, default):
        """Run a data call, turning storage failures into a signal."""
        try:
            return call()
        except DatabaseError as exc:
            self.errorOccurred.emit(str(exc))
            return default
