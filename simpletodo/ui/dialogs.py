"""The Create Project and Create Task modals."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..store import TodoStore
from ..validation import (
    DESCRIPTION_MAX_WORDS,
    NAME_MAX_LENGTH,
    count_words,
    find_hyperlink,
    sanitize_name,
    validate_description,
    validate_name,
)
from .style import SPACE_1, SPACE_2, SPACE_3, SPACE_4, SPACE_6
from .widgets import restyle

NAME_HINT = "Letters, digits, spaces and |"


class NameValidator(QValidator):
    """Silently drops any character a name may not contain, as it is typed."""

    def validate(self, text: str, pos: int):  # noqa: N802 - Qt naming
        cleaned = sanitize_name(text)[:NAME_MAX_LENGTH]
        if cleaned == text:
            return QValidator.Acceptable, text, pos
        # Keep the caret sensible when characters were removed before it.
        removed = len(text) - len(cleaned)
        return QValidator.Acceptable, cleaned, max(0, pos - removed)


def _field_label(text: str) -> QLabel:
    # Sentence case: an all-caps label shouts without adding information.
    label = QLabel(text)
    label.setObjectName("fieldLabel")
    return label


class _BaseDialog(QDialog):
    """Shared chrome: a centred title, a message line, and two buttons."""

    def __init__(
        self,
        title: str,
        store: TodoStore,
        parent: QWidget | None = None,
        *,
        commit_text: str = "Create",
    ):
        super().__init__(parent)
        self.store = store
        self.setModal(True)
        self.setWindowTitle(title)

        self._title = QLabel(title)
        self._title.setObjectName("dialogTitle")
        self._title.setAlignment(Qt.AlignCenter)

        self.message = QLabel("")
        self.message.setObjectName("errorNote")
        self.message.setAlignment(Qt.AlignCenter)
        self.message.setWordWrap(True)

        self.create_button = QPushButton(commit_text)
        self.create_button.setObjectName("primary")
        self.create_button.setCursor(Qt.PointingHandCursor)
        self.create_button.setDefault(True)
        self.create_button.clicked.connect(self._on_create)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("ghost")
        self.cancel_button.setCursor(Qt.PointingHandCursor)
        self.cancel_button.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.setSpacing(SPACE_2)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.create_button)

        self.form = QVBoxLayout()
        self.form.setSpacing(SPACE_1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACE_6, SPACE_6, SPACE_6, SPACE_6)
        outer.setSpacing(SPACE_4)
        outer.addWidget(self._title)
        outer.addLayout(self.form)
        outer.addWidget(self.message)
        outer.addLayout(buttons)

    def _set_error(self, text: str) -> None:
        self.message.setText(text)

    def _on_create(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


class CreateProjectDialog(_BaseDialog):
    """Collects a single project name."""

    created = Signal(object)

    def __init__(self, store: TodoStore, parent: QWidget | None = None) -> None:
        super().__init__("Create Project", store, parent)
        self.setMinimumWidth(380)

        self.name_edit = QLineEdit()
        self.name_edit.setValidator(NameValidator(self))
        self.name_edit.setMaxLength(NAME_MAX_LENGTH)
        self.name_edit.setPlaceholderText("Home Chores")
        self.name_edit.textChanged.connect(self._on_name_changed)
        self.name_edit.returnPressed.connect(self._on_create)

        self.hint = QLabel(NAME_HINT)
        self.hint.setObjectName("hint")

        self.form.addWidget(_field_label("Project name"))
        self.form.addWidget(self.name_edit)
        self.form.addWidget(self.hint)

        self._on_name_changed(self.name_edit.text())

    def _on_name_changed(self, text: str) -> None:
        self._set_error("")
        self.hint.setText(
            f"{len(text)}/{NAME_MAX_LENGTH}" if text else NAME_HINT
        )
        self.create_button.setEnabled(bool(text.strip()))

    def _on_create(self) -> None:
        name = self.name_edit.text().strip()
        result = validate_name(name, label="Project name")
        if not result:
            self._set_error(result.message)
            return
        if self.store.project_exists(name):
            self._set_error(f"A project called “{name}” already exists.")
            return

        project = self.store.create_project(name)
        if project is None:
            return               # the store reported the storage error already
        self.created.emit(project)
        self.accept()


class RenameDialog(_BaseDialog):
    """Rename a project or a task.

    Knows nothing about storage: it validates, then exposes `new_name`. The
    caller decides what to rename, which keeps one dialog useful for both.
    """

    def __init__(
        self,
        store: TodoStore,
        *,
        title: str,
        field_label: str,
        current_name: str,
        taken=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, store, parent, commit_text="Rename")
        self.setMinimumWidth(380)
        self._current = current_name
        self._taken = taken
        self.new_name: str | None = None

        self.name_edit = QLineEdit(current_name)
        self.name_edit.setValidator(NameValidator(self))
        self.name_edit.setMaxLength(NAME_MAX_LENGTH)
        self.name_edit.textChanged.connect(self._on_name_changed)
        self.name_edit.returnPressed.connect(self._on_create)
        self.name_edit.selectAll()

        self.hint = QLabel(NAME_HINT)
        self.hint.setObjectName("hint")

        self.form.addWidget(_field_label(field_label))
        self.form.addWidget(self.name_edit)
        self.form.addWidget(self.hint)

        self._on_name_changed(self.name_edit.text())

    def _on_name_changed(self, text: str) -> None:
        self._set_error("")
        self.hint.setText(f"{len(text)}/{NAME_MAX_LENGTH}" if text else NAME_HINT)
        stripped = text.strip()
        self.create_button.setEnabled(bool(stripped) and stripped != self._current)

    def _on_create(self) -> None:
        name = self.name_edit.text().strip()
        result = validate_name(name, label="Name")
        if not result:
            self._set_error(result.message)
            return
        if name == self._current:
            self.reject()
            return
        if self._taken is not None and self._taken(name):
            self._set_error(f"\u201c{name}\u201d is already taken.")
            return
        self.new_name = name
        self.accept()


class CreateTaskDialog(_BaseDialog):
    """Collects a task's name, description, due date and project."""

    created = Signal(object)

    def __init__(
        self,
        store: TodoStore,
        parent: QWidget | None = None,
        *,
        preselect_project_id: int | None = None,
    ) -> None:
        super().__init__("Create Task", store, parent)
        self.setMinimumWidth(420)

        # -- name
        self.name_edit = QLineEdit()
        self.name_edit.setValidator(NameValidator(self))
        self.name_edit.setMaxLength(NAME_MAX_LENGTH)
        self.name_edit.setPlaceholderText("Wash the dishes")
        self.name_edit.textChanged.connect(self._revalidate)

        self.name_hint = QLabel(NAME_HINT)
        self.name_hint.setObjectName("hint")

        # -- description
        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText("Optional detail…")
        self.description_edit.setFixedHeight(76)
        self.description_edit.setAcceptRichText(False)
        self.description_edit.textChanged.connect(self._revalidate)

        self.description_hint = QLabel("")
        self.description_hint.setObjectName("hint")

        # -- due date
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QDate.currentDate())

        # -- project
        self.project_combo = QComboBox()
        self._load_projects(preselect_project_id)

        self.form.addWidget(_field_label("Task name"))
        self.form.addWidget(self.name_edit)
        self.form.addWidget(self.name_hint)
        self.form.addSpacing(SPACE_3)
        self.form.addWidget(_field_label("Description"))
        self.form.addWidget(self.description_edit)
        self.form.addWidget(self.description_hint)
        self.form.addSpacing(SPACE_3)
        self.form.addWidget(_field_label("Complete by"))
        self.form.addWidget(self.date_edit)
        self.form.addSpacing(SPACE_3)
        self.form.addWidget(_field_label("Attach to project"))
        self.form.addWidget(self.project_combo)

        self._revalidate()

    def _load_projects(self, preselect_project_id: int | None) -> None:
        self.project_combo.clear()
        projects = self.store.projects()
        for project in projects:
            self.project_combo.addItem(project.name, project.id)
        if not projects:
            self.project_combo.addItem("No projects yet — create one first", None)
            self.project_combo.setEnabled(False)
        elif preselect_project_id is not None:
            index = self.project_combo.findData(preselect_project_id)
            if index >= 0:
                self.project_combo.setCurrentIndex(index)

    # -- live validation ------------------------------------------------

    def _revalidate(self) -> None:
        self._set_error("")
        name = self.name_edit.text()
        self.name_hint.setText(f"{len(name)}/{NAME_MAX_LENGTH}" if name else NAME_HINT)

        text = self.description_edit.toPlainText()
        words = count_words(text)
        link = find_hyperlink(text)

        over = words > DESCRIPTION_MAX_WORDS
        if link:
            self.description_hint.setText(f"links are not allowed — “{link}”")
        else:
            self.description_hint.setText(f"{words}/{DESCRIPTION_MAX_WORDS} words")
        self.description_hint.setProperty("warn", bool(over or link))
        restyle(self.description_hint)

        self.create_button.setEnabled(
            bool(name.strip())
            and not over
            and link is None
            and self.project_combo.currentData() is not None
        )

    # -- commit ---------------------------------------------------------

    def _on_create(self) -> None:
        name = self.name_edit.text().strip()
        result = validate_name(name, label="Task name")
        if not result:
            self._set_error(result.message)
            return

        description = self.description_edit.toPlainText().strip()
        result = validate_description(description)
        if not result:
            self._set_error(result.message)
            return

        project_id = self.project_combo.currentData()
        if project_id is None:
            self._set_error("Choose a project for this task.")
            return

        due: date = self.date_edit.date().toPython()
        task = self.store.create_task(
            name, due.isoformat(), int(project_id), description
        )
        if task is None:
            return
        self.created.emit(task)
        self.accept()
