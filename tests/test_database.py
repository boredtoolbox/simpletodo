import os
import sqlite3
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simpletodo.database import Database, DatabaseError  # noqa: E402
from simpletodo.dates import Bucket  # noqa: E402


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "todo.sqlite3")
    database.connect()
    yield database
    database.close()


def iso(offset: int = 0) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def test_schema_is_created_on_first_run(tmp_path):
    path = tmp_path / "fresh.sqlite3"
    assert not path.exists()
    with Database(path) as database:
        assert database.counts() == (0, 0, 0)
    assert path.exists()


def test_project_round_trip(db):
    created = db.add_project("Home|Chores")
    assert created.id is not None
    projects = db.projects()
    assert [p.name for p in projects] == ["Home|Chores"]
    assert projects[0].progress == "(0/0)"


def test_projects_without_tasks_are_still_listed(db):
    db.add_project("Empty|One")
    assert len(db.projects()) == 1


def test_projects_are_sorted_case_insensitively(db):
    for name in ("zebra", "Apple", "mango"):
        db.add_project(name)
    assert [p.name for p in db.projects()] == ["Apple", "mango", "zebra"]


def test_project_exists_ignores_case(db):
    db.add_project("Work")
    assert db.project_exists("work")
    assert not db.project_exists("Play")


def test_task_counts_track_completion(db):
    project = db.add_project("Work")
    first = db.add_task("Task|One", iso(), project.id)
    db.add_task("Task|Two", iso(1), project.id)

    assert db.projects()[0].progress == "(0/2)"
    db.set_task_completed(first.id, True)
    assert db.projects()[0].progress == "(1/2)"
    db.set_task_completed(first.id, False)
    assert db.projects()[0].progress == "(0/2)"


def test_task_carries_its_project_name(db):
    project = db.add_project("Garden")
    db.add_task("Mow|Lawn", iso(), project.id)
    assert db.tasks_for_project(project.id)[0].project_name == "Garden"


def test_description_and_dates_persist_verbatim(db):
    project = db.add_project("Notes")
    db.add_task("Write|Up", iso(3), project.id, "some detail here")
    task = db.tasks_for_project(project.id)[0]
    assert task.description == "some detail here"
    assert task.due_date == iso(3)
    # creation_date is ISO 8601 and parseable
    assert "T" in task.creation_date


def test_bucket_queries(db):
    project = db.add_project("Mixed")
    db.add_task("Over|Due", iso(-2), project.id)
    db.add_task("Due|Today", iso(0), project.id)
    db.add_task("Due|Tomorrow", iso(1), project.id)
    db.add_task("Far|Off", iso(20), project.id)

    def names(bucket, **kw):
        return {t.name for t in db.tasks_in_bucket(bucket, **kw)}

    assert names(Bucket.TODAY) == {"Over|Due", "Due|Today"}
    assert names(Bucket.TOMORROW) == {"Due|Tomorrow"}
    assert names(Bucket.THIS_WEEK) == {"Due|Today", "Due|Tomorrow"}
    assert names(Bucket.REST) == {"Far|Off"}


def test_buckets_can_exclude_completed(db):
    project = db.add_project("Mixed")
    done = db.add_task("Is|Done", iso(0), project.id)
    db.add_task("Not|Done", iso(0), project.id)
    db.set_task_completed(done.id, True)

    # The default keeps completed work visible, so (X/Y) can be counted.
    assert {t.name for t in db.tasks_in_bucket(Bucket.TODAY)} == {
        "Is|Done",
        "Not|Done",
    }
    assert [
        t.name for t in db.tasks_in_bucket(Bucket.TODAY, include_completed=False)
    ] == ["Not|Done"]


def test_completed_tasks_sort_below_outstanding_ones(db):
    project = db.add_project("Order")
    first = db.add_task("Aaa", iso(0), project.id)
    db.add_task("Zzz", iso(0), project.id)
    db.set_task_completed(first.id, True)
    assert [t.name for t in db.tasks_in_bucket(Bucket.TODAY)] == ["Zzz", "Aaa"]


def test_deleting_a_project_removes_its_tasks(db):
    project = db.add_project("Temp")
    db.add_task("Child|Task", iso(), project.id)
    db.delete_project(project.id)
    assert db.counts() == (0, 0, 0)


def test_overdue_flag(db):
    project = db.add_project("P")
    late = db.add_task("Late", iso(-1), project.id)
    task = db.tasks_for_project(project.id)[0]
    assert task.is_overdue()
    db.set_task_completed(late.id, True)
    assert not db.tasks_for_project(project.id)[0].is_overdue()


def test_changes_are_on_disk_immediately(tmp_path):
    path = tmp_path / "todo.sqlite3"
    with Database(path) as writer:
        project = writer.add_project("Persisted")
        writer.add_task("Kept", iso(), project.id)

        # A second, independent connection sees the write without a close.
        with Database(path) as reader:
            assert [p.name for p in reader.projects()] == ["Persisted"]
            assert reader.counts()[1] == 1


def test_corrupt_database_is_set_aside_and_rebuilt(tmp_path):
    path = tmp_path / "todo.sqlite3"
    path.write_bytes(b"this is definitely not a sqlite file" * 40)

    database = Database(path)
    database.connect()
    try:
        assert database.recovered_from is not None
        assert database.recovered_from.exists()
        assert ".corrupt-" in database.recovered_from.name
        assert database.counts() == (0, 0, 0)       # usable again
        database.add_project("After|Recovery")
        assert len(database.projects()) == 1
    finally:
        database.close()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_write_protected_database_reports_a_readable_error(tmp_path):
    """A read-only data folder must fail with guidance, not a traceback."""
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    with Database(blocked / "todo.sqlite3") as setup:
        setup.add_project("Existing")
    blocked.chmod(0o500)                            # read + execute, no write
    try:
        database = Database(blocked / "todo.sqlite3")
        database.connect()                          # opening is still fine
        try:
            assert [p.name for p in database.projects()] == ["Existing"]
            with pytest.raises(DatabaseError) as caught:
                database.add_project("Rejected")
            assert "permission" in str(caught.value).lower() or "read-only" in str(
                caught.value
            ).lower()
        finally:
            database.close()
    finally:
        blocked.chmod(0o700)


def test_operations_before_connect_are_refused(tmp_path):
    database = Database(tmp_path / "x.sqlite3")
    with pytest.raises(DatabaseError):
        database.projects()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_a_healthy_database_is_never_quarantined(tmp_path):
    """Regression: a read-only folder is not corruption. Data must stay put."""
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    path = blocked / "todo.sqlite3"
    with Database(path) as setup:
        setup.add_project("Precious")
    original = path.read_bytes()
    blocked.chmod(0o500)
    try:
        database = Database(path)
        database.connect()
        try:
            assert database.recovered_from is None          # nothing moved aside
            assert [p.name for p in database.projects()] == ["Precious"]
        finally:
            database.close()
    finally:
        blocked.chmod(0o700)
    assert path.exists() and path.read_bytes() == original
    assert not list(blocked.glob("*.corrupt-*"))


def test_corruption_is_distinguished_from_access_failure():
    from simpletodo.database import _is_corruption

    assert _is_corruption(sqlite3.DatabaseError("file is not a database"))
    assert _is_corruption(sqlite3.DatabaseError("database disk image is malformed"))
    assert not _is_corruption(
        sqlite3.OperationalError("attempt to write a readonly database")
    )
    assert not _is_corruption(sqlite3.OperationalError("unable to open database file"))
    assert not _is_corruption(sqlite3.OperationalError("disk I/O error"))


def test_existing_data_survives_reopening(tmp_path):
    path = tmp_path / "todo.sqlite3"
    with Database(path) as first:
        project = first.add_project("Kept")
        task = first.add_task("Still|Here", iso(2), project.id, "detail")
        first.set_task_completed(task.id, True)
    with Database(path) as second:
        assert second.counts() == (1, 1, 1)
        reread = second.tasks_for_project(second.projects()[0].id)[0]
        assert reread.name == "Still|Here"
        assert reread.description == "detail"
        assert reread.is_completed is True


def test_rename_project(db):
    project = db.add_project("Old Name")
    db.rename_project(project.id, "New Name")
    assert [p.name for p in db.projects()] == ["New Name"]


def test_rename_task(db):
    project = db.add_project("P")
    task = db.add_task("Old task", iso(), project.id)
    db.rename_task(task.id, "New task")
    assert db.tasks_for_project(project.id)[0].name == "New task"


def test_renaming_trims_surrounding_space(db):
    project = db.add_project("P")
    db.rename_project(project.id, "  Padded  ")
    assert db.projects()[0].name == "Padded"


def test_project_exists_can_exclude_one_project(db):
    first = db.add_project("Alpha")
    db.add_project("Beta")
    # Alpha keeping its own name is not a clash...
    assert not db.project_exists("Alpha", exclude_id=first.id)
    # ...but taking Beta's is.
    assert db.project_exists("Beta", exclude_id=first.id)
    assert db.project_exists("Alpha")


def test_renaming_a_project_keeps_its_tasks(db):
    project = db.add_project("Before")
    db.add_task("Kept", iso(), project.id)
    db.rename_project(project.id, "After")
    tasks = db.tasks_for_project(project.id)
    assert [t.name for t in tasks] == ["Kept"]
    assert tasks[0].project_name == "After"


def test_deleting_one_task_leaves_the_others(db):
    project = db.add_project("P")
    first = db.add_task("Goes", iso(), project.id)
    db.add_task("Stays", iso(), project.id)
    db.delete_task(first.id)
    assert [t.name for t in db.tasks_for_project(project.id)] == ["Stays"]
    assert db.projects()[0].total_tasks == 1


def test_archiving_hides_a_project_and_its_schedule(db):
    home = db.add_project("Home")
    db.add_task("Dishes", iso(0), home.id)
    db.add_task("Bins", iso(0), home.id)
    db.set_task_completed(db.all_tasks()[0].id, True)
    work = db.add_project("Work")
    db.add_task("Report", iso(0), work.id)

    db.set_project_archived(home.id, True)

    assert [p.name for p in db.projects()] == ["Work"]
    archived = db.projects(archived=True)
    assert [(p.name, p.total_tasks, p.completed_tasks) for p in archived] == [
        ("Home", 2, 1)
    ]
    assert [t.name for t in db.tasks_in_bucket(Bucket.TODAY)] == ["Report"]
    assert len(db.tasks_for_project(home.id)) == 2      # kept, not deleted
    assert db.counts() == (1, 1, 0)
    assert db.archived_count() == 1


def test_restoring_returns_everything(db):
    home = db.add_project("Home")
    db.add_task("Dishes", iso(0), home.id)
    db.set_project_archived(home.id, True)
    db.set_project_archived(home.id, False)

    assert [p.name for p in db.projects()] == ["Home"]
    assert db.projects(archived=True) == []
    assert db.counts() == (1, 1, 0)
    assert db.archived_count() == 0


def test_an_archived_name_is_still_taken(db):
    home = db.add_project("Home")
    db.set_project_archived(home.id, True)
    assert db.project_exists("home")


def test_the_newest_task_is_remembered(db):
    assert db.newest_task() is None
    home = db.add_project("Home")
    work = db.add_project("Work")
    db.add_task("A", iso(), home.id)
    assert db.newest_task().project_id == home.id
    db.add_task("B", iso(), work.id)
    db.add_task("C", iso(), None)
    assert (db.newest_task().name, db.newest_task().project_id) == ("C", None)


def test_a_task_moves_between_projects(db):
    home = db.add_project("Home")
    work = db.add_project("Work")
    task = db.add_task("A", iso(), home.id, "detail")
    db.move_task(task.id, work.id)
    assert db.tasks_for_project(home.id) == []
    [moved] = db.tasks_for_project(work.id)
    assert (moved.name, moved.description) == ("A", "detail")



# -- tasks without a project, and pinned tasks --------------------------


def test_a_task_can_belong_to_no_project(db):
    home = db.add_project("Home")
    db.add_task("Filed", iso(), home.id)
    loose = db.add_task("Loose", iso(), None)
    [reread] = db.loose_tasks()
    assert (reread.id, reread.project_id, reread.project_name) == (loose.id, None, "")
    assert [t.name for t in db.tasks_for_project(home.id)] == ["Filed"]
    assert db.counts() == (1, 2, 0)
    assert "Loose" in [t.name for t in db.tasks_in_bucket(Bucket.TODAY)]


def test_a_task_can_leave_its_project_and_come_back(db):
    home = db.add_project("Home")
    task = db.add_task("A", iso(), home.id)
    db.move_task(task.id, None)
    assert [t.name for t in db.loose_tasks()] == ["A"]
    db.move_task(task.id, home.id)
    assert db.loose_tasks() == []


def test_pinned_tasks_come_from_everywhere_but_the_archive(db):
    home = db.add_project("Home")
    old = db.add_project("Old")
    for name, project in (("Home pin", home), ("Old pin", old), ("Loose pin", None)):
        task = db.add_task(name, iso(), project.id if project else None)
        db.set_task_pinned(task.id, True)
    db.add_task("Unpinned", iso(), home.id)
    db.set_project_archived(old.id, True)
    assert sorted(t.name for t in db.pinned_tasks()) == ["Home pin", "Loose pin"]
    assert all(t.is_pinned for t in db.pinned_tasks())


def test_pinned_tasks_sort_first_but_finished_ones_still_sink(db):
    home = db.add_project("Home")
    db.add_task("Soon", iso(0), home.id)
    later = db.add_task("Later", iso(5), home.id)
    done = db.add_task("Done", iso(9), home.id)
    for task in (later, done):
        db.set_task_pinned(task.id, True)
    db.set_task_completed(done.id, True)
    assert [t.name for t in db.tasks_for_project(home.id)] == ["Later", "Soon", "Done"]
    db.set_task_pinned(later.id, False)
    assert [t.name for t in db.tasks_for_project(home.id)] == ["Soon", "Later", "Done"]


# -- upgrading a database from before those existed --------------------


def _version_0_database(path):
    """A database as the first release wrote it: a project per task, no pins."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            creation_date TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '', due_date TEXT NOT NULL,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            is_completed INTEGER NOT NULL DEFAULT 0, creation_date TEXT NOT NULL);
        INSERT INTO projects VALUES (1, 'Home', '2026-01-01T09:00:00', 1);
        INSERT INTO tasks VALUES
            (7, 'Kept', 'detail', '2030-01-01', 1, 1, '2026-01-01T09:00:00');
        """
    )
    conn.commit()
    conn.close()


def test_an_old_database_is_upgraded_and_keeps_its_data(tmp_path):
    path = tmp_path / "old.sqlite3"
    _version_0_database(path)
    with Database(path) as database:
        [task] = database.tasks_for_project(1)
        assert (task.id, task.name, task.description, task.is_completed) == (
            7, "Kept", "detail", True)
        assert task.is_pinned is False
        database.add_task("Loose", iso(), None)              # newly allowed
        database.set_task_pinned(task.id, True)
        database.delete_project(1)                           # still cascades
        assert [t.name for t in database.all_tasks()] == ["Loose"]
        assert database.conn.execute("PRAGMA user_version").fetchone()[0] == 1


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_an_old_database_that_cannot_be_written_is_left_alone(tmp_path):
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    path = blocked / "old.sqlite3"
    _version_0_database(path)
    original = path.read_bytes()
    blocked.chmod(0o500)
    try:
        with pytest.raises(DatabaseError) as caught:
            Database(path).connect()
        assert "upgrade" in str(caught.value)
    finally:
        blocked.chmod(0o700)
    assert path.read_bytes() == original
    assert not list(blocked.glob("*.corrupt-*"))
