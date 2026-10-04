"""SQLite persistence. This layer knows nothing about Qt or the UI."""

from __future__ import annotations

import logging
import shutil
import sqlite3
from datetime import date, datetime
from pathlib import Path

from . import paths
from .dates import Bucket, bucket_matches
from .models import Project, Task, now_iso

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    creation_date TEXT    NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    description   TEXT    NOT NULL DEFAULT '',
    due_date      TEXT    NOT NULL,
    project_id    INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    is_completed  INTEGER NOT NULL DEFAULT 0,
    creation_date TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_due     ON tasks(due_date);
"""


#: Phrases SQLite uses when a file is genuinely not a usable database. Anything
#: else -- a read-only folder, a missing permission, an I/O fault -- must never
#: be mistaken for corruption, or we would quarantine healthy data.
_CORRUPTION_MARKERS = (
    "file is not a database",
    "malformed",
    "file is encrypted",
    "unsupported file format",
)


def _is_corruption(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in _CORRUPTION_MARKERS)


class DatabaseError(RuntimeError):
    """A storage failure worth showing to the person using the app."""


class Database:
    """The application's data access layer.

    Every write commits immediately, so the file on disk always reflects what
    the window shows.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else paths.database_path()
        self.recovered_from: Path | None = None
        self._conn: sqlite3.Connection | None = None

    # -- lifecycle ------------------------------------------------------

    def connect(self) -> None:
        """Open the database, repairing it if the file is unusable."""
        try:
            if self.path.parent != Path("."):
                self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DatabaseError(
                f"Cannot create the data folder {self.path.parent}.\n\n{exc}"
            ) from exc

        try:
            self._open()
        except sqlite3.DatabaseError as exc:
            if not _is_corruption(exc):
                # A healthy file we simply cannot use right now.
                raise DatabaseError(self._explain(exc)) from exc
            log.warning("database is corrupt (%s); rebuilding", exc)
            self._quarantine_and_rebuild(exc)
        except OSError as exc:
            raise DatabaseError(
                f"Cannot open {self.path}.\n\n{exc}\n\n"
                "Check that you have permission to read and write that folder."
            ) from exc

    def _open(self) -> None:
        # The default rollback journal is used deliberately: a single-user app
        # gains nothing from WAL, and WAL cannot open a database that sits in a
        # folder we may only read.
        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        # Read the header first: a corrupt file raises here, before any write.
        conn.execute("PRAGMA quick_check").fetchone()
        conn.execute("PRAGMA foreign_keys = ON")
        if not self._schema_present(conn):
            conn.executescript(SCHEMA)
        self._conn = conn

    @staticmethod
    def _schema_present(conn: sqlite3.Connection) -> bool:
        """Is the schema already in place? A read-only query, always safe."""
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name IN ('projects', 'tasks')"
        ).fetchall()
        return len(rows) == 2

    def _quarantine_and_rebuild(self, cause: Exception) -> None:
        """Move a corrupt file aside and start a fresh database."""
        self._conn = None
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = self.path.with_name(f"{self.path.name}.corrupt-{stamp}")
        try:
            if self.path.exists():
                shutil.move(str(self.path), str(backup))
                self.recovered_from = backup
            for suffix in ("-wal", "-shm"):
                stray = self.path.with_name(self.path.name + suffix)
                if stray.exists():
                    stray.unlink()
        except OSError as exc:
            raise DatabaseError(
                f"The database at {self.path} is damaged and could not be "
                f"moved aside.\n\n{exc}"
            ) from exc

        try:
            self._open()
        except (sqlite3.DatabaseError, OSError) as exc:
            raise DatabaseError(
                f"The database is damaged and a replacement could not be "
                f"created.\n\n{cause}\n{exc}"
            ) from exc

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise DatabaseError("The database is not open.")
        return self._conn

    def __enter__(self) -> "Database":
        self.connect()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- projects -------------------------------------------------------

    def add_project(self, name: str) -> Project:
        project = Project(name=name.strip(), creation_date=now_iso())
        cur = self._write(
            "INSERT INTO projects (name, creation_date, is_active) VALUES (?, ?, ?)",
            (project.name, project.creation_date, int(project.is_active)),
        )
        project.id = cur.lastrowid
        return project

    def project_exists(self, name: str, exclude_id: int | None = None) -> bool:
        """Is this name taken? *exclude_id* lets a project keep its own name."""
        sql = "SELECT 1 FROM projects WHERE name = ? COLLATE NOCASE"
        params: list = [name.strip()]
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        return self._read(sql + " LIMIT 1", tuple(params)).fetchone() is not None

    def rename_project(self, project_id: int, name: str) -> None:
        self._write(
            "UPDATE projects SET name = ? WHERE id = ?", (name.strip(), project_id)
        )

    def projects(self, *, archived: bool = False) -> list[Project]:
        """Live projects (or archived ones), each with its task counts."""
        rows = self._read(
            """
            SELECT p.id, p.name, p.creation_date, p.is_active,
                   COUNT(t.id)                                AS total,
                   COALESCE(SUM(t.is_completed), 0)           AS done
            FROM projects p
            LEFT JOIN tasks t ON t.project_id = p.id
            WHERE p.is_active = ?
            GROUP BY p.id
            ORDER BY p.name COLLATE NOCASE
            """,
            (0 if archived else 1,),
        ).fetchall()
        return [
            Project(
                id=r["id"],
                name=r["name"],
                creation_date=r["creation_date"],
                is_active=bool(r["is_active"]),
                total_tasks=r["total"],
                completed_tasks=r["done"],
            )
            for r in rows
        ]

    def set_project_archived(self, project_id: int, archived: bool) -> None:
        self._write(
            "UPDATE projects SET is_active = ? WHERE id = ?",
            (0 if archived else 1, project_id),
        )

    def delete_project(self, project_id: int) -> None:
        self._write("DELETE FROM projects WHERE id = ?", (project_id,))

    # -- tasks ----------------------------------------------------------

    def add_task(
        self,
        name: str,
        due_date: str,
        project_id: int,
        description: str = "",
    ) -> Task:
        task = Task(
            name=name.strip(),
            due_date=due_date,
            project_id=project_id,
            description=description.strip(),
            creation_date=now_iso(),
        )
        cur = self._write(
            """
            INSERT INTO tasks
                (name, description, due_date, project_id, is_completed, creation_date)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                task.name,
                task.description,
                task.due_date,
                task.project_id,
                int(task.is_completed),
                task.creation_date,
            ),
        )
        task.id = cur.lastrowid
        return task

    def tasks_for_project(self, project_id: int) -> list[Task]:
        rows = self._read(
            """
            SELECT t.*, p.name AS project_name
            FROM tasks t JOIN projects p ON p.id = t.project_id
            WHERE t.project_id = ?
            ORDER BY t.is_completed, t.due_date, t.id
            """,
            (project_id,),
        ).fetchall()
        return [self._to_task(r) for r in rows]

    def all_tasks(self) -> list[Task]:
        """Every task in a live project. Archived work is out of the schedule."""
        rows = self._read(
            """
            SELECT t.*, p.name AS project_name
            FROM tasks t JOIN projects p ON p.id = t.project_id
            WHERE p.is_active = 1
            ORDER BY t.due_date, t.id
            """
        ).fetchall()
        return [self._to_task(r) for r in rows]

    def tasks_in_bucket(
        self,
        bucket: Bucket,
        today: date | None = None,
        *,
        include_completed: bool = True,
    ) -> list[Task]:
        """Tasks belonging to one date section, soonest first."""
        today = today or date.today()
        selected = [
            t
            for t in self.all_tasks()
            if bucket_matches(t.due, bucket, today)
            and (include_completed or not t.is_completed)
        ]
        selected.sort(key=lambda t: (t.is_completed, t.due, t.name.lower()))
        return selected

    def set_task_completed(self, task_id: int, completed: bool) -> None:
        self._write(
            "UPDATE tasks SET is_completed = ? WHERE id = ?",
            (int(completed), task_id),
        )

    def rename_task(self, task_id: int, name: str) -> None:
        self._write("UPDATE tasks SET name = ? WHERE id = ?", (name.strip(), task_id))

    def delete_task(self, task_id: int) -> None:
        self._write("DELETE FROM tasks WHERE id = ?", (task_id,))

    def counts(self) -> tuple[int, int, int]:
        """(projects, tasks, completed tasks) across live projects."""
        row = self._read(
            """
            SELECT (SELECT COUNT(*) FROM projects WHERE is_active = 1) AS projects,
                   COUNT(t.id)                                         AS tasks,
                   COALESCE(SUM(t.is_completed), 0)                    AS done
            FROM tasks t JOIN projects p ON p.id = t.project_id
            WHERE p.is_active = 1
            """
        ).fetchone()
        return row["projects"], row["tasks"], row["done"]

    def archived_count(self) -> int:
        row = self._read("SELECT COUNT(*) FROM projects WHERE is_active = 0")
        return row.fetchone()[0]

    # -- plumbing -------------------------------------------------------

    @staticmethod
    def _to_task(row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            due_date=row["due_date"],
            project_id=row["project_id"],
            is_completed=bool(row["is_completed"]),
            creation_date=row["creation_date"],
            project_name=row["project_name"] if "project_name" in row.keys() else "",
        )

    def _read(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        try:
            return self.conn.execute(sql, params)
        except sqlite3.Error as exc:
            raise DatabaseError(self._explain(exc)) from exc

    def _write(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        try:
            cur = self.conn.execute(sql, params)
        except sqlite3.Error as exc:
            raise DatabaseError(self._explain(exc)) from exc
        return cur

    def _explain(self, exc: sqlite3.Error) -> str:
        message = str(exc).lower()
        if "readonly" in message or "read-only" in message:
            return (
                f"The database at {self.path} is read-only, so the change was "
                "not saved.\n\nCheck the file's permissions and that the disk "
                "is not full."
            )
        if "unable to open" in message or "permission" in message:
            return (
                f"Cannot open the database at {self.path}.\n\n"
                "Check that you have permission to read and write that folder."
            )
        if "disk i/o" in message or "disk full" in message:
            return (
                f"The disk reported an error while using {self.path}.\n\n"
                "Check the available space and the health of the drive."
            )
        if isinstance(exc, sqlite3.DatabaseError) and "malformed" in str(exc).lower():
            return (
                "The database file appears to be damaged. Restart the app and "
                "it will be moved aside and rebuilt."
            )
        return f"A storage error occurred.\n\n{type(exc).__name__}: {exc}"


__all__ = ["Database", "DatabaseError"]
