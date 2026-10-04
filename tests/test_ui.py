"""Tests that drive the real widgets."""

import pytest
from PySide6.QtCore import QDate, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMenu

from simpletodo.database import Database
from simpletodo.dates import Bucket
from simpletodo.store import TodoStore
from simpletodo.ui.dialogs import CreateProjectDialog, CreateTaskDialog
from simpletodo.ui.main_window import MainWindow
from simpletodo.ui.style import stylesheet
from simpletodo.ui.widgets import CollapsibleSection, TaskRow


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
    window.resize(700, 580)
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


def sections(view) -> list[CollapsibleSection]:
    return view.column.findChildren(CollapsibleSection)


def rows(view) -> list[TaskRow]:
    return view.column.findChildren(TaskRow)


def seed(win, *, offsets=((0, "Wash|Dishes"), (-3, "Call|Plumber"), (1, "Buy|Bread"))):
    project = win.store.create_project("Home|Chores")
    for offset, name in offsets:
        due = QDate.currentDate().addDays(offset).toPython().isoformat()
        win.store.create_task(name, due, project.id)
    return project


# -- empty state --------------------------------------------------------


def test_empty_state_invites_a_first_project(win):
    texts = [l.text() for l in win.projects_view.column.findChildren(QLabel)]
    assert any("No projects yet" in t for t in texts), texts


def test_window_has_two_tabs_and_a_minimum_size(win):
    assert [win.tabs.tabText(i) for i in range(win.tabs.count())] == [
        "Projects",
        "Date",
    ]
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


# -- projects tab -------------------------------------------------------


def test_projects_tab_shows_name_and_counts(win):
    seed(win)
    win.store.create_project("Empty|One")
    titles = [s.header_text for s in sections(win.projects_view)]
    assert any("Home|Chores" in t and "(0/3)" in t for t in titles), titles
    # A project with no tasks is still listed.
    assert any("Empty|One" in t and "(0/0)" in t for t in titles), titles


def test_ticking_a_box_updates_the_database_and_the_header(win):
    seed(win)
    section = sections(win.projects_view)[0]
    section.set_expanded(True, animate=False)
    row = [r for r in rows(win.projects_view) if r.task.name == "Buy|Bread"][0]

    row.check.setChecked(True)
    spin()

    stored = [t for t in win.store.tasks_for_project(row.task.project_id)
              if t.name == "Buy|Bread"][0]
    assert stored.is_completed
    assert any("(1/3)" in s.header_text for s in sections(win.projects_view))


def test_a_completed_row_is_greyed(win):
    seed(win)
    sections(win.projects_view)[0].set_expanded(True, animate=False)
    row = [r for r in rows(win.projects_view) if r.task.name == "Buy|Bread"][0]
    row.check.setChecked(True)
    spin()
    again = [r for r in rows(win.projects_view) if r.task.name == "Buy|Bread"][0]
    assert again.check.property("done") is True


def test_an_open_section_stays_open_across_a_refresh(win):
    seed(win)
    sections(win.projects_view)[0].set_expanded(True, animate=False)
    win.store.create_project("Another|One")       # forces a rebuild
    spin()
    home = [s for s in sections(win.projects_view) if "Home|Chores" in s.header_text][0]
    assert home.expanded


def test_arrow_indicator_follows_the_state(win):
    seed(win)
    section = sections(win.projects_view)[0]
    assert "▶" in section.header_text
    section.set_expanded(True, animate=False)
    assert "▼" in section.header_text


# -- date tab -----------------------------------------------------------


def test_date_tab_has_the_four_sections_with_counts(win):
    seed(win, offsets=((0, "Due|Today"), (-3, "Over|Due"), (1, "Due|Tomorrow"),
                       (4, "This|Week"), (30, "Far|Away")))
    labels = [s.header_text for s in sections(win.date_view)]
    assert len(labels) == 4
    assert any(b.label in l for b in Bucket for l in labels)
    assert any("Today" in l and "This" not in l and "(0/2)" in l for l in labels), labels
    assert any("Tomorrow" in l and "(0/1)" in l for l in labels), labels
    assert any("This Week" in l and "(0/3)" in l for l in labels), labels
    assert any("Rest" in l and "(0/1)" in l for l in labels), labels


def test_date_rows_name_their_project_and_mark_overdue(win):
    seed(win)
    row = [r for r in rows(win.date_view) if r.task.name == "Call|Plumber"][0]
    assert row.project_label.text() == "Home|Chores"
    assert "overdue" in row.due_label.text()
    assert row.due_label.property("overdue") is True
    # Only the due note is red; the project name stays quiet.
    assert not row.project_label.property("overdue")


def test_today_section_starts_open(win):
    seed(win)
    today = [s for s in sections(win.date_view)
             if "Today" in s.header_text and "This" not in s.header_text][0]
    assert today.expanded


def test_toggling_in_one_tab_updates_the_other(win):
    seed(win)
    row = [r for r in rows(win.date_view) if r.task.name == "Call|Plumber"][0]
    row.check.setChecked(True)
    spin()
    titles = [s.header_text for s in sections(win.projects_view)]
    assert any("(1/3)" in t for t in titles), titles


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
    assert "\u2026" in shown
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


def test_no_storage_errors_during_normal_use(win):
    seed(win)
    sections(win.projects_view)[0].set_expanded(True, animate=False)
    rows(win.projects_view)[0].check.setChecked(True)
    spin()
    assert win.store_errors == []


# -- animation ----------------------------------------------------------


def test_expand_and_collapse_animate_and_settle(win):
    seed(win)
    section = sections(win.projects_view)[0]
    assert section.body.height() == 0

    section.header.click()
    spin(60)
    assert section.body.maximumHeight() > 0       # mid-flight
    spin(300)
    assert section.expanded and section.body.height() > 50

    section.header.click()
    spin(300)
    assert not section.expanded and section.body.height() == 0

    section.header.click()
    spin(300)
    assert section.expanded and section.body.height() > 50


def test_meta_text_is_available_before_the_row_is_shown(win):
    from simpletodo.models import Task
    from datetime import date, timedelta

    task = Task(
        name="Call|Plumber",
        due_date=(date.today() - timedelta(days=2)).isoformat(),
        project_id=1,
        project_name="Home|Chores",
    )
    row = TaskRow(task, show_project=True)        # never shown
    assert "Home|Chores" in row.meta_text
    assert "overdue 2d" in row.meta_text

    plain = TaskRow(task, show_project=False)
    assert "Home|Chores" not in plain.meta_text


# -- the + button and section alignment ---------------------------------


def test_add_button_sits_top_left(win):
    spin(60)
    button = win.add_button
    assert button.pos().x() < win.width() / 2, "should be on the left"
    assert button.pos().y() < win.height() / 2, "should be at the top"


def test_add_menu_opens_downward(win):
    from PySide6.QtCore import QPoint

    spin(60)
    anchor = win.add_button.mapToGlobal(QPoint(0, 0))
    win.add_button.click()
    spin(40)
    menu = [m for m in win.findChildren(QMenu) if m.isVisible()][0]
    assert menu.pos().y() >= anchor.y() + win.add_button.height()
    menu.close()


def test_tab_bar_stays_centred_in_the_window(win):
    from PySide6.QtCore import QPoint

    spin(60)
    bar = win.tabs.tabBar()
    centre = bar.mapTo(win, QPoint(bar.width() // 2, 0)).x()
    assert abs(centre - win.width() // 2) <= 2, "the + must not shift the tabs"


def test_section_headers_share_one_left_edge(win):
    seed(win)
    win.store.create_project("A much longer project name")
    win.store.create_project("Short")
    spin()
    lefts = {s.header.mapTo(win, s.header.rect().topLeft()).x()
             for s in sections(win.projects_view)}
    assert len(lefts) == 1, f"headers start at differing x: {lefts}"


def test_task_rows_are_indented_past_their_heading(win):
    seed(win)
    section = sections(win.projects_view)[0]
    section.set_expanded(True, animate=False)
    spin()
    header_x = section.header.mapTo(win, section.header.rect().topLeft()).x()
    row = rows(win.projects_view)[0]
    row_x = row.check.mapTo(win, row.check.rect().topLeft()).x()
    assert row_x > header_x, "tasks should sit in from their heading"


# -- vertical placement --------------------------------------------------


def _geometry(view):
    """(gap above, content height, gap below, viewport height)."""
    from PySide6.QtCore import QPoint

    spin(60)
    viewport = view.scroll.viewport()
    top = view.column.mapTo(viewport, QPoint(0, 0)).y()
    height = view.column.height()
    return top, height, viewport.height() - (top + height), viewport.height()


def test_a_short_list_sits_near_the_middle(win):
    for n in range(3):
        win.store.create_project(f"Project {n}")
    win.resize(700, 580)
    top, height, below, viewport = _geometry(win.projects_view)

    assert top > 60, f"content is still hugging the top bar (gap {top})"
    assert below >= 0 and top + height <= viewport, "content must fit on screen"
    assert abs(top - below) < viewport * 0.35, f"not centred: {top} vs {below}"


def test_placement_follows_the_window_size(win):
    for n in range(3):
        win.store.create_project(f"Project {n}")

    win.resize(640, 460)
    small_top, _, _, _ = _geometry(win.projects_view)
    win.resize(1400, 1000)
    large_top, _, large_below, large_viewport = _geometry(win.projects_view)

    assert large_top > small_top, "the gap should grow with the window"
    assert abs(large_top - large_below) < large_viewport * 0.35

    win.resize(640, 460)
    back_top, _, _, _ = _geometry(win.projects_view)
    assert abs(back_top - small_top) <= 2, "should return to where it was"


def test_a_long_list_anchors_to_the_top_and_scrolls(win):
    for n in range(25):
        win.store.create_project(f"Project {n:02d}")
    win.resize(700, 580)
    top, height, _, viewport = _geometry(win.projects_view)

    assert top <= 20, f"a list taller than the window must start at the top ({top})"
    assert height > viewport
    assert win.projects_view.scroll.verticalScrollBar().maximum() > 0


def test_it_recentres_when_the_list_shrinks_again(win):
    """Regression: the scroll widget kept the tallest height it had shown."""
    for n in range(25):
        win.store.create_project(f"Project {n:02d}")
    win.resize(700, 580)
    _geometry(win.projects_view)                      # render the tall list

    for project in win.store.projects()[3:]:
        win.store.delete_project(project.id)
    top, height, below, viewport = _geometry(win.projects_view)

    assert below >= 0, f"content was pushed below the fold (gap_below={below})"
    assert top + height <= viewport
    assert abs(top - below) < viewport * 0.35
    assert win.projects_view.scroll.verticalScrollBar().maximum() == 0


def test_collapsing_a_section_recentres(win):
    seed(win)
    win.resize(700, 580)
    section = sections(win.projects_view)[0]

    section.set_expanded(True, animate=False)
    _geometry(win.projects_view)
    section.set_expanded(False, animate=False)
    top, height, below, viewport = _geometry(win.projects_view)

    assert below >= 0 and top + height <= viewport
    assert abs(top - below) < viewport * 0.35


def test_the_date_tab_is_placed_the_same_way(win):
    seed(win)
    win.resize(700, 580)
    top, height, below, viewport = _geometry(win.date_view)
    assert top > 20
    assert below >= 0 and top + height <= viewport


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


def test_renaming_a_project_updates_both_tabs(win, monkeypatch):
    from simpletodo.ui import views

    seed(win)
    project = win.store.projects()[0]
    monkeypatch.setattr(views, "RenameDialog", _StubRename("Renamed Project"))
    win.projects_view._rename_project(project)
    spin()

    assert [p.name for p in win.store.projects()] == ["Renamed Project"]
    assert any("Renamed Project" in s.header_text
               for s in sections(win.projects_view))
    # The Date tab prints project names beside each task.
    assert all(r.project_label.text() == "Renamed Project"
               for r in rows(win.date_view))


def test_cancelling_a_rename_changes_nothing(win, monkeypatch):
    from simpletodo.ui import views

    seed(win)
    project = win.store.projects()[0]
    monkeypatch.setattr(views, "RenameDialog", _StubRename("Nope", accept=False))
    win.projects_view._rename_project(project)
    spin()
    assert [p.name for p in win.store.projects()] == ["Home|Chores"]


def test_renaming_a_task(win, monkeypatch):
    from simpletodo.ui import views

    seed(win)
    task = [t for t in win.store.tasks_for_project(win.store.projects()[0].id)
            if t.name == "Buy|Bread"][0]
    monkeypatch.setattr(views, "RenameDialog", _StubRename("Buy sourdough"))
    win.projects_view._rename_task(task)
    spin()

    names = {t.name for t in win.store.tasks_for_project(task.project_id)}
    assert "Buy sourdough" in names and "Buy|Bread" not in names


def test_deleting_a_project_takes_its_tasks(win, monkeypatch):
    from simpletodo.ui import views

    seed(win)
    project = win.store.projects()[0]
    monkeypatch.setattr(views.QMessageBox, "question",
                        _confirm(views.QMessageBox.Yes))
    win.projects_view._delete_project(project)
    spin()

    assert win.store.projects() == []
    assert win.store.counts() == (0, 0, 0)


def test_declining_the_delete_keeps_the_project(win, monkeypatch):
    from simpletodo.ui import views

    seed(win)
    project = win.store.projects()[0]
    monkeypatch.setattr(views.QMessageBox, "question",
                        _confirm(views.QMessageBox.No))
    win.projects_view._delete_project(project)
    spin()
    assert len(win.store.projects()) == 1
    assert win.store.counts()[1] == 3


def test_deleting_a_task_leaves_the_project(win, monkeypatch):
    from simpletodo.ui import views

    seed(win)
    project = win.store.projects()[0]
    task = win.store.tasks_for_project(project.id)[0]
    monkeypatch.setattr(views.QMessageBox, "question",
                        _confirm(views.QMessageBox.Yes))
    win.projects_view._delete_task(task)
    spin()

    assert len(win.store.projects()) == 1
    assert win.store.counts()[1] == 2


def test_a_task_can_be_deleted_from_the_date_tab_too(win, monkeypatch):
    from simpletodo.ui import views

    seed(win)
    task = rows(win.date_view)[0].task
    monkeypatch.setattr(views.QMessageBox, "question",
                        _confirm(views.QMessageBox.Yes))
    win.date_view._delete_task(task)
    spin()
    assert win.store.counts()[1] == 2


def test_rows_and_headings_carry_a_menu_button(win):
    seed(win)
    section = sections(win.projects_view)[0]
    assert section.menu_button.isVisible() or not win.isVisible()
    section.set_expanded(True, animate=False)
    spin()
    row = rows(win.projects_view)[0]

    # Hidden until hovered, but always holding its place in the layout.
    assert row.menu_button.property("revealed") is False
    row._reveal_menu(True)
    assert row.menu_button.property("revealed") is True


def test_date_sections_have_no_project_menu(win):
    seed(win)
    for section in sections(win.date_view):
        assert not section.menu_button.isVisible()


# A popped-up menu carries WA_DeleteOnClose, so inspect it before the event
# loop gets a chance to close and destroy it.


def test_task_menu_offers_rename_and_delete(win):
    from PySide6.QtCore import QPoint

    seed(win)
    task = rows(win.date_view)[0].task
    menu = win.date_view._task_menu(task, QPoint(0, 0))
    assert [a.text() for a in menu.actions()] == ["Rename…", "Delete task"]
    menu.close()


def test_project_menu_offers_rename_and_delete(win):
    from PySide6.QtCore import QPoint

    seed(win)
    project = win.store.projects()[0]
    menu = win.projects_view._project_menu(project, QPoint(0, 0))
    assert [a.text() for a in menu.actions()] == [
        "Rename…", "Archive project", "Delete project",
    ]
    menu.close()


def test_menu_delete_action_is_wired(win, monkeypatch):
    from PySide6.QtCore import QPoint
    from simpletodo.ui import views

    seed(win)
    project = win.store.projects()[0]
    monkeypatch.setattr(views.QMessageBox, "question",
                        _confirm(views.QMessageBox.Yes))
    menu = win.projects_view._project_menu(project, QPoint(0, 0))
    _action(menu, "Delete project").trigger()
    spin()
    assert win.store.projects() == []
    assert win.store.projects(archived=True) == []


def test_menu_rename_action_is_wired(win, monkeypatch):
    from PySide6.QtCore import QPoint
    from simpletodo.ui import views

    seed(win)
    project = win.store.projects()[0]
    monkeypatch.setattr(views, "RenameDialog", _StubRename("From The Menu"))
    menu = win.projects_view._project_menu(project, QPoint(0, 0))
    _action(menu, "Rename…").trigger()
    spin()
    assert [p.name for p in win.store.projects()] == ["From The Menu"]


def test_opening_a_menu_returns_instead_of_blocking(win):
    """Menus must popup(), not exec(): exec() would never return here."""
    from PySide6.QtCore import QPoint

    seed(win)
    menu = win.projects_view._project_menu(win.store.projects()[0], QPoint(0, 0))
    assert menu is not None              # reached only because popup() returned
    menu.close()


def test_the_menu_button_requests_a_menu(win):
    seed(win)
    section = sections(win.projects_view)[0]
    seen = []
    section.menuRequested.connect(seen.append)
    section.menu_button.click()
    spin(20)
    assert len(seen) == 1

    section.set_expanded(True, animate=False)
    spin()
    row = rows(win.projects_view)[0]
    row_seen = []
    row.menuRequested.connect(row_seen.append)
    row.menu_button.click()
    spin(20)
    assert len(row_seen) == 1


def test_revealing_the_menu_does_not_shift_the_row(win):
    seed(win)
    sections(win.projects_view)[0].set_expanded(True, animate=False)
    spin()
    row = rows(win.projects_view)[0]
    before = (row.check.x(), row.due_label.x())
    row._reveal_menu(True)
    spin(20)
    assert (row.check.x(), row.due_label.x()) == before


# -- task name reveals the description -----------------------------------


def _click(widget):
    """Send a real press/release to *widget*."""
    from PySide6.QtCore import QPoint, Qt
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
    sections(win.projects_view)[0].set_expanded(True, animate=False)
    spin()
    by_name = {r.task.name: r for r in rows(win.projects_view)}
    return by_name["Fix the bike"], by_name["Buy bread"]


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


def test_a_completed_task_greys_its_name(win):
    described, _ = _described_rows(win)
    described.check.setChecked(True)
    spin()
    again = {r.task.name: r for r in rows(win.projects_view)}["Fix the bike"]
    assert again.name_label.property("done") is True


def test_the_description_lines_up_with_the_task_name(win):
    from PySide6.QtCore import QPoint

    described, _ = _described_rows(win)
    described.set_description_shown(True, animate=False)
    spin()
    name_x = described.name_label.mapTo(described, QPoint(0, 0)).x()
    text_x = described.description_label.mapTo(described, QPoint(0, 0)).x()
    assert abs(name_x - text_x) <= 2, f"name at {name_x}, description at {text_x}"


def test_the_description_opens_in_the_date_tab_too(win):
    _described_rows(win)
    win.tabs.setCurrentWidget(win.date_view)
    spin()
    # A task due today appears under both Today and This Week; take the one in
    # the open section, since a row in a closed section has no clickable area.
    today = [s for s in sections(win.date_view)
             if "Today" in s.header_text and "This" not in s.header_text][0]
    row = {r.task.name: r for r in today.findChildren(TaskRow)}["Fix the bike"]
    assert today.expanded

    _click(row.name_label)
    spin(260)
    assert row.description_shown
    assert not row.check.isChecked()


def test_a_row_in_a_closed_section_ignores_clicks(win):
    """The click guard is the hit rect, so a clipped row cannot be opened."""
    described, _ = _described_rows(win)
    section = sections(win.projects_view)[0]
    section.set_expanded(False, animate=False)
    spin(260)

    row = {r.task.name: r for r in rows(win.projects_view)}["Fix the bike"]
    _click(row.name_label)
    spin(260)
    assert not row.description_shown


def test_revealing_a_description_keeps_the_list_on_screen(win):
    described, _ = _described_rows(win)
    win.resize(700, 580)
    described.set_description_shown(True, animate=False)
    top, height, below, viewport = _geometry(win.projects_view)
    assert below >= 0 and top + height <= viewport


# -- masthead, typewriter face and paper ---------------------------------


def test_the_masthead_reads_simple_to_do(win):
    assert win.title_label.text() == "Simple To Do"


def test_the_masthead_persists_across_tabs(win):
    spin()
    assert win.title_label.isVisible()
    win.tabs.setCurrentWidget(win.date_view)
    spin()
    assert win.title_label.isVisible(), "the heading vanished on the Date tab"
    win.tabs.setCurrentWidget(win.projects_view)
    spin()
    assert win.title_label.isVisible()


def test_the_masthead_lives_outside_the_tab_widget(win):
    """Inside the tabs it would be swapped out with the page."""
    assert not win.tabs.isAncestorOf(win.title_label)


def test_the_masthead_uses_a_typewriter_face(win):
    from PySide6.QtGui import QFontInfo
    from simpletodo.ui.style import TYPEWRITER_FAMILIES, resolve_typewriter_family

    family = resolve_typewriter_family()
    assert family, "no typewriter family resolved"
    assert family in stylesheet(), "the stylesheet does not bind the face"

    spin()
    rendered = QFontInfo(win.title_label.font()).family()
    assert rendered, "the heading has no resolved font"
    # Either a face we asked for, or at least a fixed-pitch stand-in.
    assert (
        rendered in TYPEWRITER_FAMILIES
        or QFontInfo(win.title_label.font()).fixedPitch()
    ), f"heading rendered in {rendered!r}"


def test_the_paper_texture_ships_with_the_package():
    from pathlib import Path

    from simpletodo.ui.style import PAPER_URL

    asset = Path(PAPER_URL)
    assert asset.exists(), f"missing {asset}"
    assert asset.stat().st_size > 0


def test_the_paper_is_warm_and_not_white():
    from PySide6.QtGui import QColor

    from simpletodo.ui.style import PAPER

    assert PAPER.upper() != "#FFFFFF", "the background is plain white"
    colour = QColor(PAPER)
    assert colour.red() > colour.blue(), "paper should be warm, not cool"
    assert colour.red() > 240, "paper should still be light"


def test_the_grain_tiles_across_the_whole_backdrop(app):
    """Regression: `background-image` + `background-repeat` paints one tile.

    Only the `background: url(...) repeat` shorthand tiles in this Qt, so a
    large window would otherwise show grain in one corner and flat colour
    everywhere else.
    """
    from PySide6.QtWidgets import QWidget

    backdrop = QWidget()
    backdrop.setObjectName("appBackdrop")
    backdrop.setStyleSheet(stylesheet())
    backdrop.resize(900, 700)
    image = backdrop.grab().toImage()

    def variance(x0, y0):
        values = [
            image.pixelColor(x, y).red()
            for y in range(y0, y0 + 40)
            for x in range(x0, x0 + 40)
        ]
        mean = sum(values) / len(values)
        return sum((v - mean) ** 2 for v in values) / len(values)

    corners = [(20, 20), (840, 20), (20, 640), (840, 640), (430, 330)]
    for x, y in corners:
        assert variance(x, y) > 1.0, f"no grain at ({x}, {y}) - tiling is broken"


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
    from PySide6.QtCore import Qt

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
    from PySide6.QtCore import QPoint, Qt

    seed(win)
    menu = win.projects_view._project_menu(win.store.projects()[0], QPoint(0, 0))
    assert menu.testAttribute(Qt.WA_TranslucentBackground)
    assert menu.windowFlags() & Qt.FramelessWindowHint
    menu.close()


def test_the_menu_radius_is_in_the_stylesheet():
    from simpletodo.ui.style import MENU_RADIUS

    assert MENU_RADIUS > 0
    assert f"border-radius: {MENU_RADIUS}px" in stylesheet()


# -- archive ------------------------------------------------------------


def _archive_first_project(win):
    from PySide6.QtCore import QPoint

    menu = win.projects_view._project_menu(win.store.projects()[0], QPoint(0, 0))
    _action(menu, "Archive project").trigger()
    spin()


def test_archiving_moves_a_project_out_of_both_tabs(win):
    seed(win)
    _archive_first_project(win)

    assert sections(win.projects_view) == []
    assert rows(win.date_view) == []
    archived = sections(win.archive_view)
    assert len(archived) == 1 and "Home|Chores" in archived[0].header_text


def test_archived_tasks_are_kept_and_visible_in_the_archive(win):
    seed(win)
    _archive_first_project(win)
    section = sections(win.archive_view)[0]
    section.set_expanded(True, animate=False)
    names = sorted(r.task.name for r in rows(win.archive_view))
    assert names == ["Buy|Bread", "Call|Plumber", "Wash|Dishes"]


def test_restoring_brings_a_project_back(win):
    from PySide6.QtCore import QPoint

    seed(win)
    _archive_first_project(win)
    archived = win.store.projects(archived=True)[0]
    menu = win.archive_view._project_menu(archived, QPoint(0, 0))
    assert [a.text() for a in menu.actions()] == [
        "Rename…", "Restore project", "Delete project",
    ]
    _action(menu, "Restore project").trigger()
    spin()

    assert sections(win.archive_view) == []
    assert [p.name for p in win.store.projects()] == ["Home|Chores"]
    assert len(rows(win.date_view)) >= 3


def test_archived_projects_are_not_offered_for_new_tasks(win):
    seed(win)
    win.store.create_project("Garden")
    _archive_first_project(win)          # "Garden" sorts first
    dialog = CreateTaskDialog(win.store, win)
    offered = [dialog.project_combo.itemText(i) for i in range(dialog.project_combo.count())]
    assert offered == ["Home|Chores"]


def test_the_archive_button_swaps_the_tabs_for_the_archive(win):
    assert win.tabs.isVisible() and not win.archive_view.isVisible()

    win.archive_button.click()
    spin()
    assert win.archive_button.isChecked()
    assert win.archive_view.isVisible() and win.archive_heading.isVisible()
    assert not win.tabs.isVisible()

    win.archive_button.click()
    spin()
    assert win.tabs.isVisible() and not win.archive_view.isVisible()


def test_the_archive_button_sits_under_the_plus(win):
    from PySide6.QtCore import QPoint

    plus = win.add_button.mapTo(win, QPoint(0, 0))
    box = win.archive_button.mapTo(win, QPoint(0, 0))
    assert box.x() == plus.x()
    assert box.y() >= plus.y() + win.add_button.height()


def test_an_empty_archive_says_how_to_fill_it(win):
    texts = [l.text() for l in win.archive_view.column.findChildren(QLabel)]
    assert any("Nothing archived" in t for t in texts), texts


def test_creating_a_project_leaves_the_archive(win, monkeypatch):
    from simpletodo.ui import main_window

    class _Accept:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return 1

    monkeypatch.setattr(main_window, "CreateProjectDialog", _Accept)
    win.show_archive(True)
    win.create_project()
    assert not win.archive_view.isVisible()
    assert win.tabs.currentWidget() is win.projects_view


def test_status_bar_counts_live_work_and_notes_the_archive(win):
    seed(win)
    _archive_first_project(win)
    assert win.counts_label.text().startswith("0 projects")
    assert "1 archived" in win.counts_label.text()


def test_the_archive_icon_is_crisp_on_retina(win):
    from PySide6.QtCore import QSize

    icon = win.archive_button.icon()
    retina = icon.pixmap(QSize(18, 18), 2.0)
    assert retina.width() == 36 and retina.devicePixelRatio() == 2.0


def test_the_archive_glyph_takes_its_ink_from_the_tokens():
    from simpletodo.ui.style import INK_SOFT, archive_icon_svg

    assert INK_SOFT.encode() in archive_icon_svg()


def _tab_centre(win, index):
    bar = win.tabs.tabBar()
    return bar, bar.tabRect(index).center()


def test_the_tabs_stay_visible_as_the_way_back(win):
    win.show_archive(True)
    spin()
    assert win.tabs.tabBar().isVisible()


def test_clicking_the_current_tab_leaves_the_archive(win):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    win.show_archive(True)
    spin()
    bar, centre = _tab_centre(win, win.tabs.currentIndex())
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier, centre)
    spin()
    assert not win.archive_view.isVisible() and win.tabs.isVisible()
    assert not win.archive_button.isChecked()


def test_clicking_the_other_tab_leaves_the_archive_for_that_tab(win):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    win.show_archive(True)
    spin()
    bar, centre = _tab_centre(win, 1)
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier, centre)
    spin()
    assert not win.archive_view.isVisible()
    assert win.tabs.currentWidget() is win.date_view


def test_escape_leaves_the_archive(win):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    win.show_archive(True)
    spin()
    QTest.keyClick(win, Qt.Key_Escape)
    spin()
    assert not win.archive_view.isVisible()


def test_only_the_archive_label_is_underlined_while_open(win):
    from simpletodo.ui.style import ACCENT

    win.show_archive(True)
    spin()
    image = win.grab().toImage()
    image.setDevicePixelRatio(1)
    scale = image.width() / win.width()
    bar = win.tabs.tabBar()
    accent = ACCENT.lower()

    def underlined(widget, rect):
        top_left = widget.mapTo(win, rect.bottomLeft())
        y = int((top_left.y() - 1) * scale)
        xs = range(int(top_left.x() * scale), int((top_left.x() + rect.width()) * scale))
        return any(image.pixelColor(x, y).name() == accent for x in xs)

    assert underlined(win.archive_heading, win.archive_heading.rect())
    assert not underlined(bar, bar.tabRect(bar.currentIndex()))
