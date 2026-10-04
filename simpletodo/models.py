"""Plain data objects mirroring the two database tables."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


def now_iso() -> str:
    """Current local time as an ISO 8601 string, to the second."""
    return datetime.now().isoformat(timespec="seconds")


def parse_date(value: str) -> date:
    """Read an ISO 8601 date (tolerating a full datetime)."""
    return date.fromisoformat(value[:10])


@dataclass
class Project:
    name: str
    id: int | None = None
    creation_date: str = field(default_factory=now_iso)
    is_active: bool = True

    #: Populated by the data layer; not a stored column.
    total_tasks: int = 0
    completed_tasks: int = 0

    @property
    def progress(self) -> str:
        return f"({self.completed_tasks}/{self.total_tasks})"


@dataclass
class Task:
    name: str
    due_date: str                      # ISO 8601 date, YYYY-MM-DD
    project_id: int
    id: int | None = None
    description: str = ""
    is_completed: bool = False
    creation_date: str = field(default_factory=now_iso)

    #: Populated when a task is read alongside its project.
    project_name: str = ""

    @property
    def due(self) -> date:
        return parse_date(self.due_date)

    def is_overdue(self, today: date | None = None) -> bool:
        return not self.is_completed and self.due < (today or date.today())
