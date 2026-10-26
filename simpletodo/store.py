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

    #: Projects or tasks were added, removed, renamed or archived. Views
    #: rebuild. One signal, not one per table: every view shows both, so two
    #: signals meant every view rebuilt twice per change.
    changed = Signal()
    #: A task was ticked or unticked. Nothing appears or disappears, so views
    #: update the rows in place -- rebuilding them all made the tick lag.
    taskCompleted = Signal(int, bool)
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

    def last_task_project_id(self) -> int | None:
        return self._guard(self._db.last_task_project_id, default=None)

    def project_exists(self, name: str, exclude_id: int | None = None) -> bool:
        return self._guard(
            lambda: self._db.project_exists(name, exclude_id), default=False
        )

    # -- writes ---------------------------------------------------------

    def create_project(self, name: str) -> Project | None:
        project = self._guard(lambda: self._db.add_project(name), default=None)
        if project is not None:
            self.changed.emit()
        return project

    def create_task(
        self, name: str, due_date: str, project_id: int, description: str = ""
    ) -> Task | None:
        task = self._guard(
            lambda: self._db.add_task(name, due_date, project_id, description),
            default=None,
        )
        if task is not None:
            self.changed.emit()
        return task

    def rename_project(self, project_id: int, name: str) -> bool:
        ok = self._guard(
            lambda: (self._db.rename_project(project_id, name), True)[1], default=False
        )
        if ok:
            self.changed.emit()
        return bool(ok)

    def rename_task(self, task_id: int, name: str) -> bool:
        ok = self._guard(
            lambda: (self._db.rename_task(task_id, name), True)[1], default=False
        )
        if ok:
            self.changed.emit()
        return bool(ok)

    def move_task(self, task_id: int, project_id: int) -> bool:
        ok = self._guard(
            lambda: (self._db.move_task(task_id, project_id), True)[1], default=False
        )
        if ok:
            self.changed.emit()
        return bool(ok)

    def set_task_completed(self, task_id: int, completed: bool) -> bool:
        ok = self._guard(
            lambda: (self._db.set_task_completed(task_id, completed), True)[1],
            default=False,
        )
        if ok:
            self.taskCompleted.emit(task_id, completed)
        return bool(ok)

    def delete_task(self, task_id: int) -> bool:
        ok = self._guard(
            lambda: (self._db.delete_task(task_id), True)[1], default=False
        )
        if ok:
            self.changed.emit()
        return bool(ok)

    def delete_project(self, project_id: int) -> bool:
        ok = self._guard(
            lambda: (self._db.delete_project(project_id), True)[1], default=False
        )
        if ok:
            self.changed.emit()
        return bool(ok)

    def set_project_archived(self, project_id: int, archived: bool) -> bool:
        ok = self._guard(
            lambda: (self._db.set_project_archived(project_id, archived), True)[1],
            default=False,
        )
        if ok:
            self.changed.emit()
        return bool(ok)

    # -- plumbing -------------------------------------------------------

    def _guard(self, call, default):
        """Run a data call, turning storage failures into a signal."""
        try:
            return call()
        except DatabaseError as exc:
            self.errorOccurred.emit(str(exc))
            return default
