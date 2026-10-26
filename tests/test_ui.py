"""Tests that drive the real widgets."""

import pytest
from PySide6.QtCore import QDate, QEventLoop, QPoint, Qt, QTimer
from PySide6.QtWidgets import QApplication, QMenu

from simpletodo.database import Database
from simpletodo.dates import Bucket
from simpletodo.store import TodoStore
from simpletodo.ui.dialogs import CreateProjectDialog, CreateTaskDialog
from simpletodo.ui.main_window import MainWindow
from simpletodo.ui.style import stylesheet
from simpletodo.ui.views import Mode
from simpletodo.ui.widgets import TaskRow


@pytest.fixture(scope="session")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setStyle("Fusion")
    instance.setStyleSheet(stylesheet())
    return instance


@pytest.fixture
def win(app, tmp_path):
    db = Database(tmp_path / "ui.sqlite3")
    db.connect()
    store = TodoStore(db)
    errors: list[str] = []
    store.errorOccurred.connect(errors.append)
    window = MainWindow(store)
    window.resize(860, 580)
    window.show()
    window.store_errors = errors          # surfaced for assertions
    yield window

    # A dialog left open is modal and would block the next test's popups.
    for widget in list(QApplication.instance().topLevelWidgets()):
        if widget is not window and widget.isVisible():
            widget.close()
    window.close()
    spin(0)
    db.close()


def spin(ms: int = 50) -> None:
    """Let the event loop run for a moment."""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def items(win):
    return win.browser.sidebar.items


def item(win, title):
    return next(i for i in items(win) if i.title == title)


def details(win) -> dict[str, str]:
    """Each sidebar item's second line, by title."""
    return {i.title: i.detail_text for i in items(win)}


def rows(win) -> list[TaskRow]:
    return win.browser.pane.rows


def row(win, name) -> TaskRow:
    return next(r for r in rows(win) if r.task.name == name)


def choose(win, title):
    win.browser.select(item(win, title).key)


def seed(win, *, offsets=((0, "Wash|Dishes"), (-3, "Call|Plumber"), (1, "Buy|Bread"))):
    project = win.store.create_project("Home|Chores")
    for offset, name in offsets:
        due = QDate.currentDate().addDays(offset).toPython().isoformat()
        win.store.create_task(name, due, project.id)
    return project


# -- empty state --------------------------------------------------------


def test_empty_state_invites_a_first_project(win):
    assert items(win) == []
    assert "No projects yet" in win.browser.pane.message.text()
    assert win.browser.pane.message.isVisible()


def test_window_offers_the_views_and_a_minimum_size(win):
    assert [b.text() for b in win.segments.values()] == ["Projects", "Date", "Archive"]
    assert win.segments[Mode.PROJECTS].isChecked()
    assert win.minimumWidth() >= 600
    assert win.minimumHeight() >= 400


# -- create project dialog ---------------------------------------------


def test_project_dialog_creates_a_project(win):
    dialog = CreateProjectDialog(win.store, win)
    dialog.name_edit.setText("Home|Chores")
    assert dialog.create_button.isEnabled()
    dialog._on_create()
    assert dialog.result() == 1
    assert [p.name for p in win.store.projects()] == ["Home|Chores"]


def test_project_dialog_filters_forbidden_characters_as_typed(win):
    dialog = CreateProjectDialog(win.store, win)
    dialog.name_edit.setText("Bad Name!-@2")
    assert dialog.name_edit.text() == "Bad Name2"     # the space survives
    dialog.name_edit.setText("ok|name")
    assert dialog.name_edit.text() == "ok|name"


def test_names_with_spaces_round_trip(win):
    dialog = CreateProjectDialog(win.store, win)
    dialog.name_edit.setText("Home Chores")
    dialog._on_create()
    assert dialog.result() == 1
    assert [p.name for p in win.store.projects()] == ["Home Chores"]

    task_dialog = CreateTaskDialog(win.store, win)
    task_dialog.name_edit.setText("Wash the dishes")
    assert task_dialog.create_button.isEnabled()
    task_dialog._on_create()
    assert task_dialog.result() == 1
    project = win.store.projects()[0]
    assert win.store.tasks_for_project(project.id)[0].name == "Wash the dishes"


def test_project_dialog_enforces_the_length_cap(win):
    dialog = CreateProjectDialog(win.store, win)
    dialog.name_edit.setText("x" * 80)
    assert len(dialog.name_edit.text()) == 50


def test_project_dialog_blocks_an_empty_name(win):
    dialog = CreateProjectDialog(win.store, win)
    assert not dialog.create_button.isEnabled()


def test_project_dialog_rejects_a_duplicate(win):
    win.store.create_project("Home|Chores")
    dialog = CreateProjectDialog(win.store, win)
    dialog.name_edit.setText("home|chores")
    dialog._on_create()
    assert dialog.result() != 1
    assert "already exists" in dialog.message.text()


# -- create task dialog -------------------------------------------------


def test_task_dialog_creates_a_task(win):
    project = win.store.create_project("Work|Items")
    dialog = CreateTaskDialog(win.store, win)
    dialog.name_edit.setText("File|Taxes")
    dialog.description_edit.setPlainText("before the deadline")
    dialog.date_edit.setDate(QDate.currentDate().addDays(3))
    dialog.project_combo.setCurrentIndex(dialog.project_combo.findData(project.id))
    assert dialog.create_button.isEnabled()
    dialog._on_create()
    assert dialog.result() == 1

    task = win.store.tasks_for_project(project.id)[0]
    assert task.name == "File|Taxes"
    assert task.description == "before the deadline"
    assert task.due_date == QDate.currentDate().addDays(3).toPython().isoformat()


def test_task_dialog_defaults_to_today(win):
    win.store.create_project("P")
    dialog = CreateTaskDialog(win.store, win)
    assert dialog.date_edit.date() == QDate.currentDate()


def test_task_dialog_blocks_links_in_the_description(win):
    win.store.create_project("P")
    dialog = CreateTaskDialog(win.store, win)
    dialog.name_edit.setText("Linky")
    dialog.description_edit.setPlainText("read https://example.com for more")
    assert not dialog.create_button.isEnabled()
    assert "links are not allowed" in dialog.description_hint.text()


def test_task_dialog_counts_words_live_and_caps_at_300(win):
    win.store.create_project("P")
    dialog = CreateTaskDialog(win.store, win)
    dialog.name_edit.setText("Wordy")

    dialog.description_edit.setPlainText(" ".join(["word"] * 300))
    assert "300/300 words" in dialog.description_hint.text()
    assert dialog.create_button.isEnabled()

    dialog.description_edit.setPlainText(" ".join(["word"] * 301))
    assert "301/300 words" in dialog.description_hint.text()
    assert not dialog.create_button.isEnabled()


def test_task_dialog_without_projects_cannot_create(win):
    dialog = CreateTaskDialog(win.store, win)
    assert not dialog.project_combo.isEnabled()
    assert dialog.project_combo.currentData() is None
    assert not dialog.create_button.isEnabled()


# -- projects view ------------------------------------------------------


def test_sidebar_lists_projects_with_counts_and_the_next_task(win):
    seed(win)
    win.store.create_project("Empty|One")
    shown = details(win)
    # Tasks run by due date, so the overdue one is next.
    assert shown["Home|Chores"] == "0/3  Call|Plumber"
    # A project with no tasks is still listed.
    assert shown["Empty|One"] == "0/0  No tasks"


def test_the_first_project_is_selected_and_shown(win):
    seed(win)
    assert item(win, "Home|Chores").selected
    assert win.browser.pane.title_label.text() == "Home|Chores"
    assert sorted(r.task.name for r in rows(win)) == [
        "Buy|Bread", "Call|Plumber", "Wash|Dishes",
    ]


def test_selecting_a_project_shows_its_tasks(win):
    seed(win)
    other = win.store.create_project("Garden")
    win.store.create_task("Mow", "2030-01-01", other.id)
    item(win, "Garden").mousePressEvent(_press())
    assert item(win, "Garden").selected and not item(win, "Home|Chores").selected
    assert [r.task.name for r in rows(win)] == ["Mow"]
    assert win.browser.pane.title_label.text() == "Garden"


def test_an_empty_project_says_so_in_the_pane(win):
    win.store.create_project("Empty|One")
    assert rows(win) == []
    assert win.browser.pane.title_label.text() == "Empty|One"
    texts = [w.text() for w in win.browser.pane.column.findChildren(type(win.title_label))]
    assert "No tasks yet." in texts


def test_ticking_a_box_updates_the_database_and_the_sidebar(win):
    seed(win)
    row(win, "Buy|Bread").check.setChecked(True)
    spin()

    stored = [t for t in win.store.tasks_for_project(row(win, "Buy|Bread").task.project_id)
              if t.name == "Buy|Bread"][0]
    assert stored.is_completed
    assert details(win)["Home|Chores"].startswith("1/3")
    assert win.browser.pane.subtitle_label.text() == "1 of 3 done"


def test_a_completed_row_is_greyed(win):
    seed(win)
    row(win, "Buy|Bread").check.setChecked(True)
    spin()
    done = row(win, "Buy|Bread")
    assert done.check.property("done") is True
    assert done.name_label.property("done") is True


def test_the_preview_skips_finished_tasks(win):
    project = win.store.create_project("Solo")
    task = win.store.create_task("Only|One", "2030-01-01", project.id)
    win.store.set_task_completed(task.id, True)
    spin()
    assert details(win)["Solo"] == "1/1  All done"


def test_the_selection_survives_a_refresh(win):
    seed(win)
    win.store.create_project("Another|One")
    choose(win, "Home|Chores")
    win.store.create_project("Third|One")          # forces a rebuild
    spin()
    assert item(win, "Home|Chores").selected
    assert win.browser.pane.title_label.text() == "Home|Chores"


def test_deleting_the_selected_project_selects_another(win, monkeypatch):
    from simpletodo.ui import views

    seed(win)
    win.store.create_project("Zebra")
    choose(win, "Home|Chores")
    monkeypatch.setattr(views, "confirm", _confirm(True))
    win.browser._delete_project(win.store.projects()[0])
    spin()
    assert [i.title for i in items(win)] == ["Zebra"]
    assert item(win, "Zebra").selected


def test_arrow_keys_move_the_selection(win):
    from PySide6.QtTest import QTest

    for name in ("Alpha", "Beta", "Gamma"):
        win.store.create_project(name)
    sidebar = win.browser.sidebar
    choose(win, "Alpha")

    QTest.keyClick(sidebar, Qt.Key_Down)
    assert item(win, "Beta").selected
    QTest.keyClick(sidebar, Qt.Key_Down)
    QTest.keyClick(sidebar, Qt.Key_Down)           # stops at the end
    assert item(win, "Gamma").selected
    QTest.keyClick(sidebar, Qt.Key_Up)
    assert item(win, "Beta").selected
    assert win.browser.pane.title_label.text() == "Beta"


def test_dividers_clear_beside_the_selection(win):
    for name in ("Alpha", "Beta", "Gamma", "Delta"):
        win.store.create_project(name)
    choose(win, "Beta")                         # sorted: Alpha Beta Delta Gamma
    dividers = win.browser.sidebar._dividers
    assert [bool(d.property("clear")) for d in dividers] == [True, True, False]
    # Cleared, not hidden: hiding would shift every item below by a pixel.
    assert all(d.height() == 1 for d in dividers)


# -- date view ----------------------------------------------------------


def test_date_view_lists_the_four_buckets_with_counts(win):
    seed(win, offsets=((0, "Due|Today"), (-3, "Over|Due"), (1, "Due|Tomorrow"),
                       (4, "This|Week"), (30, "Far|Away")))
    win.show_mode(Mode.DATE)
    shown = details(win)
    assert list(shown) == [b.label for b in Bucket]
    assert shown["Today"].startswith("0/2")
    assert shown["Tomorrow"].startswith("0/1")
    assert shown["This Week"].startswith("0/3")
    assert shown["Rest"].startswith("0/1")


def test_today_is_selected_on_arrival(win):
    seed(win)
    win.show_mode(Mode.DATE)
    assert item(win, "Today").selected
    assert win.browser.pane.title_label.text() == "Today"
    # Overdue work is surfaced alongside today's.
    assert {r.task.name for r in rows(win)} == {"Wash|Dishes", "Call|Plumber"}


def test_date_rows_name_their_project_and_mark_overdue(win):
    seed(win)
    win.show_mode(Mode.DATE)
    late = row(win, "Call|Plumber")
    assert late.project_label.text() == "Home|Chores"
    assert "overdue" in late.due_label.text()
    assert late.due_label.property("overdue") is True
    # Only the due note is red; the project name stays quiet.
    assert not late.project_label.property("overdue")


def test_date_items_have_no_menu(win):
    seed(win)
    win.show_mode(Mode.DATE)
    assert all(i.menu_button.isHidden() for i in items(win))


def test_ticking_in_one_view_shows_in_the_other(win):
    seed(win)
    win.show_mode(Mode.DATE)
    row(win, "Call|Plumber").check.setChecked(True)
    spin()
    win.show_mode(Mode.PROJECTS)
    assert details(win)["Home|Chores"].startswith("1/3")
    assert row(win, "Call|Plumber").check.isChecked()


def test_ticking_a_box_updates_in_place_instead_of_rebuilding(win):
    """A rebuild destroyed the clicked checkbox and lagged ~1s on macOS."""
    seed(win)
    before = {id(w) for w in rows(win) + items(win)}
    target = row(win, "Wash|Dishes")

    target.check.setChecked(True)
    spin()

    assert {id(w) for w in rows(win) + items(win)} == before
    assert target in rows(win) and target.check.isChecked()
    assert win.store_errors == []


def test_a_tick_reaches_every_bucket_count(win):
    seed(win)
    win.show_mode(Mode.DATE)
    row(win, "Wash|Dishes").check.setChecked(True)
    spin()

    # Due today, so it counts in both Today and This Week.
    shown = details(win)
    assert shown["Today"].startswith("1/2")
    assert shown["This Week"].startswith("1/2")
    assert win.browser.pane.subtitle_label.text() == "1 of 2 done"
    assert "1 done" in win.counts_label.text()


def test_unticking_works_in_place_too(win):
    seed(win)
    target = row(win, "Wash|Dishes")
    target.check.setChecked(True)
    spin()
    target.check.setChecked(False)
    spin()
    stored = win.store.tasks_for_project(target.task.project_id)
    assert not any(t.is_completed for t in stored)
    assert not target.name_label.property("done")
    assert details(win)["Home|Chores"].startswith("0/3")


def test_completing_an_overdue_task_clears_its_overdue_note(win):
    seed(win)
    win.show_mode(Mode.DATE)
    late = row(win, "Call|Plumber")
    assert late.due_label.property("overdue") is True
    late.check.setChecked(True)
    spin()
    assert late.due_label.property("overdue") is False
    assert "overdue" not in late.due_label.text()


def test_each_change_is_announced_once(win):
    """Two signals per change meant every view rebuilt twice."""
    seed(win)
    changed, ticked = [], []
    win.store.changed.connect(lambda: changed.append(1))
    win.store.taskCompleted.connect(lambda *a: ticked.append(a))

    project = win.store.projects()[0]
    win.store.create_task("One|More", "2030-01-01", project.id)
    assert len(changed) == 1

    task = win.store.tasks_for_project(project.id)[0]
    win.store.set_task_completed(task.id, True)
    assert len(changed) == 1 and ticked == [(task.id, True)]


def test_each_view_remembers_its_own_selection(win):
    seed(win)
    win.store.create_project("Garden")
    choose(win, "Home|Chores")
    win.show_mode(Mode.DATE)
    choose(win, "Tomorrow")
    win.show_mode(Mode.PROJECTS)
    assert item(win, "Home|Chores").selected
    win.show_mode(Mode.DATE)
    assert item(win, "Tomorrow").selected


# -- chrome -------------------------------------------------------------


def test_status_bar_counts_everything(win):
    seed(win)
    assert "1 project" in win.counts_label.text()
    assert "3 tasks" in win.counts_label.text()


def test_status_bar_shows_where_the_database_lives(win):
    path = win.store.database_path
    assert win.db_path_label.toolTip() == str(path)
    assert win.db_path_label.displayed_text().endswith(path.name)


def test_a_long_database_path_shrinks_instead_of_the_counts(win):
    seed(win)
    win.db_path_label.setText("/very/long" * 40 + "/todo.sqlite3")
    win.resize(win.minimumWidth(), win.height())
    spin()

    counts, path = win.counts_label, win.db_path_label
    assert counts.width() >= counts.sizeHint().width()
    assert counts.geometry().right() < path.geometry().left()
    shown = path.displayed_text()
    assert "…" in shown
    assert shown.endswith("todo.sqlite3")
    assert path.fontMetrics().horizontalAdvance(shown) <= path.contentsRect().width()


def test_the_database_path_abbreviates_home():
    from pathlib import Path
    from simpletodo.ui.main_window import _display_path

    assert _display_path(Path.home() / "a" / "todo.sqlite3") == "~/a/todo.sqlite3"
    assert _display_path(Path("/srv/todo.sqlite3")) == "/srv/todo.sqlite3"


def test_add_button_offers_both_choices(win):
    win.add_button.click()
    spin(40)
    menus = [m for m in win.findChildren(QMenu) if m.isVisible()]
    assert menus, "the + button showed no menu"
    assert [a.text() for a in menus[0].actions()] == [
        "Create Project",
        "Create Task",
    ]
    menus[0].close()


def test_add_button_sits_top_left(win):
    spin(60)
    button = win.add_button.mapTo(win, QPoint(0, 0))
    assert button.x() < win.width() / 2, "should be on the left"
    assert button.y() < win.height() / 2, "should be at the top"


def test_add_menu_opens_downward(win):
    spin(60)
    anchor = win.add_button.mapToGlobal(QPoint(0, 0))
    win.add_button.click()
    spin(40)
    menu = [m for m in win.findChildren(QMenu) if m.isVisible()][0]
    assert menu.pos().y() >= anchor.y() + win.add_button.height()
    menu.close()


def test_no_storage_errors_during_normal_use(win):
    seed(win)
    rows(win)[0].check.setChecked(True)
    spin()
    assert win.store_errors == []


def _stand_in(make):
    """A dialog class whose exec() creates via *make* and announces it."""

    class _Accept:
        def __init__(self, *args, **kwargs):
            self.created = _Signal()

        def exec(self):
            self.created.emit(make())
            return 1

    return _Accept


def test_creating_a_project_selects_it(win, monkeypatch):
    from simpletodo.ui import main_window

    seed(win)
    monkeypatch.setattr(main_window, "CreateProjectDialog",
                        _stand_in(lambda: win.store.create_project("Zebra")))
    win.create_project()
    spin()
    assert item(win, "Zebra").selected
    assert win.browser.pane.title_label.text() == "Zebra"


def test_creating_a_task_from_the_archive_shows_its_project(win, monkeypatch):
    from simpletodo.ui import main_window

    project = seed(win)
    win.store.create_project("Garden")
    win.show_archive(True)
    monkeypatch.setattr(main_window, "CreateTaskDialog", _stand_in(
        lambda: win.store.create_task("New|One", "2030-01-01", project.id)))
    win.create_task()
    spin()
    assert win.mode is Mode.PROJECTS and win.segments[Mode.PROJECTS].isChecked()
    assert item(win, "Home|Chores").selected
    assert "New|One" in [r.task.name for r in rows(win)]


class _Signal:
    """Enough of a Qt signal for a stand-in dialog."""

    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args):
        for slot in self._slots:
            slot(*args)


# -- layout -------------------------------------------------------------


def test_the_sidebar_keeps_its_width_and_the_pane_takes_the_rest(win):
    from simpletodo.ui.style import SIDEBAR_WIDTH

    seed(win)
    for width in (win.minimumWidth(), 1400):
        win.resize(width, 600)
        spin()
        column = win.browser.sidebar.parentWidget()
        assert column.width() == SIDEBAR_WIDTH
        pane = win.browser.pane
        assert pane.mapTo(win, QPoint(0, 0)).x() >= SIDEBAR_WIDTH
        assert abs(pane.mapTo(win, QPoint(pane.width(), 0)).x() - win.width()) <= 1


def test_a_long_task_list_scrolls_instead_of_squashing(win):
    project = win.store.create_project("Busy")
    for n in range(40):
        win.store.create_task(f"Task {n:02d}", "2030-01-01", project.id)
    win.resize(700, 580)
    spin(80)
    assert len(rows(win)) == 40
    assert all(r.height() >= r.sizeHint().height() for r in rows(win))
    assert win.browser.pane.scroll.verticalScrollBar().maximum() > 0


def test_a_long_project_list_scrolls_the_sidebar(win):
    for n in range(30):
        win.store.create_project(f"Project {n:02d}")
    win.resize(700, 580)
    spin(80)
    assert all(i.height() >= i.sizeHint().height() for i in items(win))
    assert win.browser.sidebar.scroll.verticalScrollBar().maximum() > 0


def test_a_short_list_starts_at_the_top(win):
    seed(win)
    spin(60)
    first = rows(win)[0]
    y = first.mapTo(win.browser.pane, QPoint(0, 0)).y()
    assert y < 150, f"tasks should sit under the heading, not mid-pane ({y})"


def test_long_sidebar_text_is_elided_not_clipped(win):
    from simpletodo.ui.style import SIDEBAR_WIDTH

    win.store.create_project("A" * 50)
    spin(60)
    entry = items(win)[0]
    shown = entry.title_label.displayed_text()
    assert shown.endswith("…")
    assert entry.width() <= SIDEBAR_WIDTH


# -- renaming and deleting ----------------------------------------------


class _StubRename:
    """Stands in for RenameDialog: accepts with a chosen name, or cancels."""

    def __init__(self, name, *, accept=True):
        self.new_name = name
        self._accept = accept

    def __call__(self, *args, **kwargs):
        return self

    def exec(self):
        return 1 if self._accept else 0


def _confirm(answer):
    return lambda *args, **kwargs: answer


def _action(menu, text):
    """A menu action by its label -- positions shift as menus grow."""
    return next(a for a in menu.actions() if a.text() == text)


def _press():
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent

    return QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(5, 5),
                       QPointF(5, 5), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)


def test_rename_dialog_validates_like_create(win):
    from simpletodo.ui.dialogs import RenameDialog

    dialog = RenameDialog(
        win.store, title="Rename Project", field_label="Project name",
        current_name="Home Chores", parent=win,
    )
    # Unchanged name offers nothing to do.
    assert not dialog.create_button.isEnabled()

    dialog.name_edit.setText("Bad!Name@")
    assert dialog.name_edit.text() == "BadName"      # filtered as typed
    assert dialog.create_button.isEnabled()

    dialog.name_edit.setText("   ")
    assert not dialog.create_button.isEnabled()


def test_rename_dialog_rejects_a_taken_name(win):
    from simpletodo.ui.dialogs import RenameDialog

    dialog = RenameDialog(
        win.store, title="Rename Project", field_label="Project name",
        current_name="Alpha", taken=lambda name: name == "Beta", parent=win,
    )
    dialog.name_edit.setText("Beta")
    dialog._on_create()
    assert dialog.result() != 1
    assert "already taken" in dialog.message.text()
    assert dialog.new_name is None


def test_rename_dialog_reports_the_new_name(win):
    from simpletodo.ui.dialogs import RenameDialog

    dialog = RenameDialog(
        win.store, title="Rename Task", field_label="Task name",
        current_name="Old", parent=win,
    )
    dialog.name_edit.setText("New name")
    dialog._on_create()
    assert dialog.result() == 1
    assert dialog.new_name == "New name"


def test_renaming_a_project_updates_sidebar_pane_and_date_rows(win, monkeypatch):
    from simpletodo.ui import views

    seed(win)
    project = win.store.projects()[0]
    monkeypatch.setattr(views, "RenameDialog", _StubRename("Renamed Project"))
    win.browser._rename_project(project)
    spin()

    assert [p.name for p in win.store.projects()] == ["Renamed Project"]
    assert item(win, "Renamed Project").selected
    assert win.browser.pane.title_label.text() == "Renamed Project"
    # The Date view prints project names beside each task.
    win.show_mode(Mode.DATE)
    assert all(r.project_label.text() == "Renamed Project" for r in rows(win))


def test_cancelling_a_rename_changes_nothing(win, monkeypatch):
    from simpletodo.ui import views

    seed(win)
    project = win.store.projects()[0]
    monkeypatch.setattr(views, "RenameDialog", _StubRename("Nope", accept=False))
    win.browser._rename_project(project)
    spin()
    assert [p.name for p in win.store.projects()] == ["Home|Chores"]


def test_renaming_a_task(win, monkeypatch):
    from simpletodo.ui import views

    seed(win)
    task = row(win, "Buy|Bread").task
    monkeypatch.setattr(views, "RenameDialog", _StubRename("Buy sourdough"))
    win.browser._rename_task(task)
    spin()

    names = {t.name for t in win.store.tasks_for_project(task.project_id)}
    assert "Buy sourdough" in names and "Buy|Bread" not in names
    assert "Buy sourdough" in [r.task.name for r in rows(win)]


def test_deleting_a_project_takes_its_tasks(win, monkeypatch):
    from simpletodo.ui import views

    seed(win)
    project = win.store.projects()[0]
    monkeypatch.setattr(views, "confirm", _confirm(True))
    win.browser._delete_project(project)
    spin()

    assert win.store.projects() == []
    assert win.store.counts() == (0, 0, 0)
    assert "No projects yet" in win.browser.pane.message.text()


def test_declining_the_delete_keeps_the_project(win, monkeypatch):
    from simpletodo.ui import views

    seed(win)
    project = win.store.projects()[0]
    monkeypatch.setattr(views, "confirm", _confirm(False))
    win.browser._delete_project(project)
    spin()
    assert len(win.store.projects()) == 1
    assert win.store.counts()[1] == 3


def test_deleting_a_task_leaves_the_project(win, monkeypatch):
    from simpletodo.ui import views

    seed(win)
    task = rows(win)[0].task
    monkeypatch.setattr(views, "confirm", _confirm(True))
    win.browser._delete_task(task)
    spin()

    assert len(win.store.projects()) == 1
    assert win.store.counts()[1] == 2
    assert len(rows(win)) == 2


def test_a_task_can_be_deleted_from_the_date_view_too(win, monkeypatch):
    from simpletodo.ui import views

    seed(win)
    win.show_mode(Mode.DATE)
    task = rows(win)[0].task
    monkeypatch.setattr(views, "confirm", _confirm(True))
    win.browser._delete_task(task)
    spin()
    assert win.store.counts()[1] == 2


def test_rows_and_project_items_carry_a_menu_button(win):
    seed(win)
    entry = items(win)[0]
    assert not entry.menu_button.isHidden()
    target = rows(win)[0]

    # Hidden until hovered, but always holding its place in the layout.
    assert target.menu_button.property("revealed") is False
    target._reveal_menu(True)
    assert target.menu_button.property("revealed") is True


# A popped-up menu carries WA_DeleteOnClose, so inspect it before the event
# loop gets a chance to close and destroy it.


def test_task_menu_offers_rename_and_delete(win):
    seed(win)
    menu = win.browser._task_menu(rows(win)[0].task, QPoint(0, 0))
    assert [a.text() for a in menu.actions()] == ["Rename…", "Delete task"]
    menu.close()


def test_project_menu_offers_rename_archive_and_delete(win):
    seed(win)
    menu = win.browser._project_menu(win.store.projects()[0], QPoint(0, 0))
    assert [a.text() for a in menu.actions()] == [
        "Rename…", "Archive project", "Delete project",
    ]
    menu.close()


def test_menu_delete_action_is_wired(win, monkeypatch):
    from simpletodo.ui import views

    seed(win)
    monkeypatch.setattr(views, "confirm", _confirm(True))
    menu = win.browser._project_menu(win.store.projects()[0], QPoint(0, 0))
    _action(menu, "Delete project").trigger()
    spin()
    assert win.store.projects() == []
    assert win.store.projects(archived=True) == []


def test_menu_rename_action_is_wired(win, monkeypatch):
    from simpletodo.ui import views

    seed(win)
    monkeypatch.setattr(views, "RenameDialog", _StubRename("From The Menu"))
    menu = win.browser._project_menu(win.store.projects()[0], QPoint(0, 0))
    _action(menu, "Rename…").trigger()
    spin()
    assert [p.name for p in win.store.projects()] == ["From The Menu"]


def test_opening_a_menu_returns_instead_of_blocking(win):
    """Menus must popup(), not exec(): exec() would never return here."""
    seed(win)
    menu = win.browser._project_menu(win.store.projects()[0], QPoint(0, 0))
    assert menu is not None              # reached only because popup() returned
    menu.close()


def test_the_menu_buttons_request_menus(win):
    seed(win)
    entry = items(win)[0]
    seen = []
    entry.menuRequested.connect(seen.append)
    entry.menu_button.click()
    spin(20)
    assert len(seen) == 1

    target = rows(win)[0]
    row_seen = []
    target.menuRequested.connect(row_seen.append)
    target.menu_button.click()
    spin(20)
    assert len(row_seen) == 1


def test_the_sidebar_menu_opens_for_the_right_project(win):
    seed(win)
    win.store.create_project("Garden")
    opened = []
    win.browser._project_menu = lambda project, position: opened.append(project.name)
    item(win, "Home|Chores").menu_button.click()
    spin(20)
    assert opened == ["Home|Chores"]


def test_revealing_the_menu_does_not_shift_the_row(win):
    seed(win)
    spin()
    target = rows(win)[0]
    before = (target.check.x(), target.due_label.x())
    target._reveal_menu(True)
    spin(20)
    assert (target.check.x(), target.due_label.x()) == before


# -- task name reveals the description -----------------------------------


def _click(widget):
    """Send a real press/release to *widget*."""
    from PySide6.QtGui import QMouseEvent

    where = QPoint(5, 5)
    globally = widget.mapToGlobal(where)
    for kind in (QMouseEvent.Type.MouseButtonPress, QMouseEvent.Type.MouseButtonRelease):
        QApplication.instance().sendEvent(
            widget,
            QMouseEvent(kind, where, globally, Qt.LeftButton, Qt.LeftButton,
                        Qt.NoModifier),
        )


def _described_rows(win):
    """A project with one described task and one without."""
    project = win.store.create_project("Home Chores")
    today = QDate.currentDate().toPython().isoformat()
    win.store.create_task("Fix the bike", today, project.id,
                          "Front tyre is flat and needs a new inner tube.")
    win.store.create_task("Buy bread", today, project.id)
    spin()
    return row(win, "Fix the bike"), row(win, "Buy bread")


def test_clicking_the_name_does_not_complete_the_task(win):
    described, _ = _described_rows(win)
    assert not described.check.isChecked()

    _click(described.name_label)
    spin(260)

    assert not described.check.isChecked(), "clicking the name completed the task"
    stored = win.store.tasks_for_project(described.task.project_id)
    assert not any(t.is_completed for t in stored)


def test_clicking_the_name_reveals_and_hides_the_description(win):
    described, _ = _described_rows(win)
    assert not described.description_shown
    assert described.description_panel.height() == 0

    _click(described.name_label)
    spin(260)
    assert described.description_shown
    assert described.description_panel.height() > 10
    assert "inner tube" in described.description_label.text()

    _click(described.name_label)
    spin(260)
    assert not described.description_shown
    assert described.description_panel.height() == 0


def test_a_task_without_a_description_does_nothing(win):
    _, plain = _described_rows(win)
    assert plain.name_label.property("expandable") is False

    _click(plain.name_label)
    spin(260)

    assert not plain.description_shown
    assert plain.description_panel.height() == 0
    assert not plain.check.isChecked()


def test_the_checkbox_carries_no_label_of_its_own(win):
    """The name must be a separate widget, or clicking it would toggle."""
    described, _ = _described_rows(win)
    assert described.check.text() == ""
    assert described.name_label.text() == "Fix the bike"
    assert described.check.accessibleName() == "Fix the bike"


def test_the_checkbox_still_completes_the_task(win):
    described, _ = _described_rows(win)
    described.check.setChecked(True)
    spin()
    stored = [t for t in win.store.tasks_for_project(described.task.project_id)
              if t.name == "Fix the bike"][0]
    assert stored.is_completed


def test_the_description_lines_up_with_the_task_name(win):
    described, _ = _described_rows(win)
    described.set_description_shown(True, animate=False)
    spin()
    name_x = described.name_label.mapTo(described, QPoint(0, 0)).x()
    text_x = described.description_label.mapTo(described, QPoint(0, 0)).x()
    assert abs(name_x - text_x) <= 2, f"name at {name_x}, description at {text_x}"


def test_the_description_opens_in_the_date_view_too(win):
    _described_rows(win)
    win.show_mode(Mode.DATE)
    spin()
    described = row(win, "Fix the bike")
    _click(described.name_label)
    spin(260)
    assert described.description_shown
    assert not described.check.isChecked()


def test_revealing_a_description_pushes_the_rows_below_down(win):
    described, plain = _described_rows(win)     # same day: listed in order made
    spin()
    below = plain.mapTo(win.browser.pane, QPoint(0, 0)).y()
    assert below > described.mapTo(win.browser.pane, QPoint(0, 0)).y()
    described.set_description_shown(True, animate=False)
    spin()
    assert plain.mapTo(win.browser.pane, QPoint(0, 0)).y() > below


# -- masthead and type --------------------------------------------------


def test_the_masthead_reads_simple_to_do(win):
    assert win.title_label.text() == "Simple To Do"


def test_the_masthead_persists_across_views(win):
    for mode in Mode:
        win.show_mode(mode)
        spin()
        assert win.title_label.isVisible(), f"the heading vanished in {mode}"


def test_inter_ships_with_its_licence():
    from simpletodo.ui.style import FONT_FILES, FONTS_DIR

    for name in FONT_FILES:
        assert (FONTS_DIR / name).stat().st_size > 0, f"missing {name}"
    assert "SIL OPEN FONT LICENSE" in (FONTS_DIR / "LICENSE.txt").read_text().upper()


def test_text_is_set_in_the_bundled_inter(win):
    from PySide6.QtGui import QFont, QFontInfo

    assert '"Inter"' in stylesheet(), "the stylesheet does not bind Inter"
    spin()
    title = QFontInfo(win.title_label.font())
    assert title.family() == "Inter", f"masthead rendered in {title.family()!r}"
    assert title.weight() >= QFont.Bold
    seed(win)
    name = QFontInfo(rows(win)[0].name_label.font())
    assert name.family() == "Inter"


def test_the_ground_is_white_like_notes():
    from simpletodo.ui.style import SURFACE

    assert SURFACE.upper() == "#FFFFFF"


# -- round checkboxes ---------------------------------------------------


def test_the_checkbox_is_round_and_fills_with_the_accent(win):
    from PySide6.QtGui import QColor

    from simpletodo.ui.style import ACCENT, CHECKBOX_SIZE

    seed(win)
    target = rows(win)[0]
    target.check.setChecked(True)
    spin()
    image = target.check.grab().toImage()
    image.setDevicePixelRatio(1)
    scale = image.width() / target.check.width()
    top = (target.check.height() - CHECKBOX_SIZE) / 2

    def at(x, y):
        return image.pixelColor(int(x * scale), int((top + y) * scale))

    # The corner of the indicator's box is outside the circle; a point inside
    # the ring, clear of the tick, is the accent.
    assert at(1, 1).name() != QColor(ACCENT).name(), "the indicator is square"
    assert at(CHECKBOX_SIZE * 0.5, 3).name() == QColor(ACCENT).name()


# -- rounded popups ------------------------------------------------------


def _corner_alphas(menu):
    """Alpha at the four corners of a rendered popup."""
    image = menu.grab().toImage()
    w, h = image.width(), image.height()
    return [
        image.pixelColor(0, 0).alpha(),
        image.pixelColor(w - 1, 0).alpha(),
        image.pixelColor(0, h - 1).alpha(),
        image.pixelColor(w - 1, h - 1).alpha(),
    ], image


def test_the_add_menu_is_a_translucent_frameless_popup(win):
    """Both are required: without them border-radius never shows."""
    win.add_button.click()
    spin(40)
    menu = [m for m in win.findChildren(QMenu) if m.isVisible()][0]
    assert menu.testAttribute(Qt.WA_TranslucentBackground)
    assert menu.windowFlags() & Qt.FramelessWindowHint
    menu.close()


def test_the_add_menu_corners_are_actually_rounded(win):
    win.add_button.click()
    spin(40)
    menu = [m for m in win.findChildren(QMenu) if m.isVisible()][0]
    alphas, image = _corner_alphas(menu)

    assert image.hasAlphaChannel()
    assert all(a == 0 for a in alphas), f"corners not cut away: {alphas}"
    centre = image.pixelColor(image.width() // 2, image.height() // 2)
    assert centre.alpha() == 255, "the menu body should be solid"
    menu.close()


def test_context_menus_are_rounded_too(win):
    seed(win)
    menu = win.browser._project_menu(win.store.projects()[0], QPoint(0, 0))
    assert menu.testAttribute(Qt.WA_TranslucentBackground)
    assert menu.windowFlags() & Qt.FramelessWindowHint
    menu.close()


def test_the_menu_radius_is_in_the_stylesheet():
    from simpletodo.ui.style import MENU_RADIUS

    assert MENU_RADIUS > 0
    assert f"border-radius: {MENU_RADIUS}px" in stylesheet()


# -- archive ------------------------------------------------------------


def _archive_first_project(win):
    menu = win.browser._project_menu(win.store.projects()[0], QPoint(0, 0))
    _action(menu, "Archive project").trigger()
    spin()


def test_archiving_moves_a_project_out_of_projects_and_dates(win):
    seed(win)
    _archive_first_project(win)

    assert items(win) == []
    win.show_mode(Mode.DATE)
    assert all(i.detail_text.startswith("0/0") for i in items(win))
    win.show_archive(True)
    assert [i.title for i in items(win)] == ["Home|Chores"]


def test_archived_tasks_are_kept_and_visible_in_the_archive(win):
    seed(win)
    _archive_first_project(win)
    win.show_archive(True)
    assert item(win, "Home|Chores").selected
    assert sorted(r.task.name for r in rows(win)) == [
        "Buy|Bread", "Call|Plumber", "Wash|Dishes",
    ]
    assert win.browser.pane.subtitle_label.text().startswith("Archived")


def test_restoring_brings_a_project_back(win):
    seed(win)
    _archive_first_project(win)
    win.show_archive(True)               # restoring happens from inside it
    archived = win.store.projects(archived=True)[0]
    menu = win.browser._project_menu(archived, QPoint(0, 0))
    assert [a.text() for a in menu.actions()] == [
        "Rename…", "Restore project", "Delete project",
    ]
    _action(menu, "Restore project").trigger()
    spin()

    assert items(win) == []
    assert [p.name for p in win.store.projects()] == ["Home|Chores"]
    win.show_mode(Mode.DATE)
    assert details(win)["Today"].startswith("0/2")


def test_archived_projects_are_not_offered_for_new_tasks(win):
    seed(win)
    win.store.create_project("Garden")
    _archive_first_project(win)          # "Garden" sorts first
    dialog = CreateTaskDialog(win.store, win)
    offered = [dialog.project_combo.itemText(i) for i in range(dialog.project_combo.count())]
    assert offered == ["Home|Chores"]


def test_the_archive_is_a_segment_beside_projects_and_date(win):
    win.segments[Mode.ARCHIVE].click()
    spin()
    assert win.mode is Mode.ARCHIVE
    assert win.segments[Mode.ARCHIVE].isChecked()
    assert not win.segments[Mode.PROJECTS].isChecked()

    win.segments[Mode.DATE].click()
    spin()
    assert win.mode is Mode.DATE and not win.segments[Mode.ARCHIVE].isChecked()


def test_an_empty_archive_says_how_to_fill_it(win):
    win.show_archive(True)
    assert "Nothing archived" in win.browser.pane.message.text()


def test_escape_leaves_the_archive_for_the_view_it_came_from(win):
    from PySide6.QtTest import QTest

    win.show_mode(Mode.DATE)
    win.show_archive(True)
    # A window shortcut only fires in the active window. Detaching removed
    # sidebar items once left the window impossible to activate; see _discard.
    win.activateWindow()
    assert QTest.qWaitForWindowActive(win)
    QTest.keyClick(win, Qt.Key_Escape)
    spin()
    assert win.mode is Mode.DATE and win.segments[Mode.DATE].isChecked()


def test_creating_a_project_leaves_the_archive(win, monkeypatch):
    from simpletodo.ui import main_window

    win.show_archive(True)
    monkeypatch.setattr(main_window, "CreateProjectDialog",
                        _stand_in(lambda: win.store.create_project("Fresh")))
    win.create_project()
    spin()
    assert win.mode is Mode.PROJECTS
    assert win.segments[Mode.PROJECTS].isChecked()
    assert item(win, "Fresh").selected


def test_status_bar_counts_live_work_and_notes_the_archive(win):
    seed(win)
    _archive_first_project(win)
    assert win.counts_label.text().startswith("0 projects")
    assert "1 archived" in win.counts_label.text()


# -- strikethrough and the icon's blue ----------------------------------


def test_a_completed_task_is_struck_through(win):
    seed(win)
    target = row(win, "Buy|Bread")
    assert not target.name_label.font().strikeOut()
    target.check.setChecked(True)
    spin()
    assert target.name_label.font().strikeOut()
    target.check.setChecked(False)
    spin()
    assert not target.name_label.font().strikeOut()


def test_the_accent_is_the_app_icons_blue():
    from pathlib import Path

    from PySide6.QtGui import QColor, QImage

    from simpletodo.ui.style import ACCENT

    icon = QImage(str(Path(__file__).resolve().parent.parent / "simpletodoappimage.jpg"))
    sample = icon.pixelColor(icon.width() // 2, icon.height() // 8)
    accent = QColor(ACCENT)
    assert all(abs(a - b) <= 8 for a, b in zip(
        (sample.red(), sample.green(), sample.blue()),
        (accent.red(), accent.green(), accent.blue()),
    )), f"icon {sample.name()} vs accent {ACCENT}"


# -- the top bar --------------------------------------------------------


def test_both_halves_of_the_top_bar_share_one_height(win):
    spin()
    assert win.sidebar_bar.height() == win.browser.top_bar.height() > 0
    top = win.browser.top_bar.mapTo(win, QPoint(0, 0)).y()
    assert top == win.sidebar_bar.mapTo(win, QPoint(0, 0)).y() == 0


def test_the_new_task_button_files_under_the_selected_project(win, monkeypatch):
    from simpletodo.ui import main_window

    seed(win)
    garden = win.store.create_project("Garden")
    choose(win, "Garden")
    opened = []

    class _Spy:
        def __init__(self, store, parent, *, preselect_project_id=None):
            opened.append(preselect_project_id)
            self.created = _Signal()

        def exec(self):
            return 0

    monkeypatch.setattr(main_window, "CreateTaskDialog", _Spy)
    win.browser.compose_button.click()
    assert opened == [garden.id]

    win.show_mode(Mode.DATE)                 # no project in view
    win.browser.compose_button.click()
    assert opened == [garden.id, None]


def test_the_more_button_opens_the_selected_projects_menu(win):
    seed(win)
    win.store.create_project("Garden")
    choose(win, "Home|Chores")
    opened = []
    win.browser._project_menu = lambda project, position: opened.append(project.name)
    win.browser.more_button.click()
    assert opened == ["Home|Chores"]


def test_the_more_button_is_off_without_a_project(win):
    assert not win.browser.more_button.isEnabled()       # nothing yet
    seed(win)
    assert win.browser.more_button.isEnabled()
    win.show_mode(Mode.DATE)
    assert not win.browser.more_button.isEnabled()


def test_search_filters_the_tasks_in_view(win):
    project = seed(win)
    win.store.create_task("Fix bike", "2030-01-01", project.id, "needs a new inner tube")
    spin()
    win.browser.search_field.setText("BREAD")
    assert [r.task.name for r in rows(win) if not r.isHidden()] == ["Buy|Bread"]
    win.browser.search_field.setText("tube")              # descriptions too
    assert [r.task.name for r in rows(win) if not r.isHidden()] == ["Fix bike"]

    win.browser.search_field.setText("zzz")
    assert all(r.isHidden() for r in rows(win))
    assert not win.browser.pane._no_match.isHidden()

    win.browser.search_field.clear()
    assert not any(r.isHidden() for r in rows(win))
    assert win.browser.pane._no_match.isHidden()


def test_search_survives_switching_project(win):
    seed(win)
    other = win.store.create_project("Garden")
    win.store.create_task("Buy seeds", "2030-01-01", other.id)
    win.store.create_task("Mow", "2030-01-01", other.id)
    win.browser.search_field.setText("buy")
    choose(win, "Garden")
    assert [r.task.name for r in rows(win) if not r.isHidden()] == ["Buy seeds"]


def test_the_top_bar_buttons_are_round(win):
    from simpletodo.ui.style import TOOL_SIZE

    button = win.browser.compose_button
    assert button.height() == TOOL_SIZE
    assert f"border-radius: {TOOL_SIZE // 2}px" in stylesheet()


# -- dialogs look like a Notes sheet ------------------------------------


def test_dialog_labels_sit_left_of_their_fields(win):
    win.store.create_project("P")
    dialog = CreateTaskDialog(win.store, win)
    dialog.show()
    spin()
    grid = dialog.fields
    for field in (dialog.name_edit, dialog.description_edit, dialog.date_edit,
                  dialog.project_combo):
        row_index, column, _, _ = grid.getItemPosition(grid.indexOf(field))
        label = grid.itemAtPosition(row_index, 0).widget()
        assert column == 1 and label.text().endswith(":")
        assert label.geometry().right() < field.geometry().left()
    dialog.close()


def test_dialogs_have_cancel_left_of_the_commit_button(win):
    dialog = CreateProjectDialog(win.store, win)
    dialog.show()
    spin()
    cancel = dialog.cancel_button.mapTo(dialog, QPoint(0, 0))
    commit = dialog.create_button.mapTo(dialog, QPoint(0, 0))
    assert cancel.y() == commit.y() and cancel.x() < commit.x()
    assert commit.x() + dialog.create_button.width() > dialog.width() * 0.8
    dialog.close()


def test_a_destructive_confirm_defaults_to_cancel(win):
    from simpletodo.ui.dialogs import MessageDialog

    dialog = MessageDialog("Delete Project", "Delete it?", win,
                           confirm_text="Delete", destructive=True)
    assert dialog.cancel_button.isDefault() and not dialog.create_button.isDefault()
    assert dialog.create_button.text() == "Delete"


def test_a_notice_has_a_single_button(win):
    from simpletodo.ui.dialogs import MessageDialog

    dialog = MessageDialog("Storage Problem", "Disk full.", win, cancel_text=None)
    assert dialog.cancel_button.isHidden()
    dialog.create_button.click()
    assert dialog.result() == 1


def test_dialogs_open_as_sheets_only_on_macos(win):
    from PySide6.QtGui import QGuiApplication

    dialog = CreateProjectDialog(win.store, win)
    is_sheet = (dialog.windowFlags() & Qt.Sheet) == Qt.Sheet
    assert is_sheet == (QGuiApplication.platformName() == "cocoa")


def test_creating_a_task_with_no_projects_offers_a_project_first(win, monkeypatch):
    from simpletodo.ui import main_window

    asked = []
    monkeypatch.setattr(main_window, "confirm",
                        lambda *a, **k: asked.append(k["confirm_text"]) or False)
    win.create_task()
    assert asked == ["New Project"]


# -- the task dialog remembers the last project -------------------------


def _file_task(win, name, project_id=None):
    dialog = CreateTaskDialog(win.store, win)
    if project_id is not None:
        dialog.project_combo.setCurrentIndex(dialog.project_combo.findData(project_id))
    dialog.name_edit.setText(name)
    dialog._on_create()
    assert dialog.result() == 1
    return dialog


def test_the_next_task_starts_in_the_last_tasks_project(win):
    win.store.create_project("Alpha")              # sorts first: the old default
    beta = win.store.create_project("Beta")
    _file_task(win, "One", beta.id)

    again = CreateTaskDialog(win.store, win)
    assert again.project_combo.currentData() == beta.id


def test_the_project_can_still_be_changed(win):
    alpha = win.store.create_project("Alpha")
    beta = win.store.create_project("Beta")
    _file_task(win, "One", beta.id)
    _file_task(win, "Two", alpha.id)               # changed it by hand
    assert CreateTaskDialog(win.store, win).project_combo.currentData() == alpha.id


def test_the_remembered_project_beats_the_one_in_view(win):
    alpha = win.store.create_project("Alpha")
    beta = win.store.create_project("Beta")
    _file_task(win, "One", beta.id)
    dialog = CreateTaskDialog(win.store, win, preselect_project_id=alpha.id)
    assert dialog.project_combo.currentData() == beta.id


def test_the_memory_survives_a_restart(app, tmp_path):
    path = tmp_path / "restart.sqlite3"
    first = Database(path)
    first.connect()
    store = TodoStore(first)
    store.create_project("Alpha")
    beta = store.create_project("Beta")
    store.create_task("One", "2030-01-01", beta.id)
    first.close()

    second = Database(path)
    second.connect()
    dialog = CreateTaskDialog(TodoStore(second))
    assert dialog.project_combo.currentData() == beta.id
    second.close()


def test_an_archived_last_project_falls_back(win):
    alpha = win.store.create_project("Alpha")
    beta = win.store.create_project("Beta")
    _file_task(win, "One", beta.id)
    win.store.set_project_archived(beta.id, True)

    dialog = CreateTaskDialog(win.store, win, preselect_project_id=alpha.id)
    assert dialog.project_combo.currentData() == alpha.id
