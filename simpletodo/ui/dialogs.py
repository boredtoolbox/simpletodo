"""The dialogs: create, rename, and the confirm/notice sheet."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QValidator
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
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
from .style import FIELD_HEIGHT, SPACE_1, SPACE_2, SPACE_3, SPACE_4, SPACE_6
from .widgets import DatePicker, MenuComboBox, restyle

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
    # Sentence case with a colon, as a Mac sheet labels its fields.
    label = QLabel(f"{text}:")
    label.setObjectName("fieldLabel")
    return label


class _BaseDialog(QDialog):
    """Shared chrome, laid out like a Notes sheet.

    A bold title at the top left; fields in a grid with their labels to the
    left; a hairline; Cancel and the commit button at the bottom right. On
    macOS it opens as a sheet sliding out of the window's title bar.
    """

    def __init__(
        self,
        title: str,
        store: TodoStore | None = None,
        parent: QWidget | None = None,
        *,
        commit_text: str = "Create",
    ):
        super().__init__(parent)
        self.store = store
        self.setModal(True)
        self.setWindowTitle(title)
        if parent is not None and QGuiApplication.platformName() == "cocoa":
            self.setWindowFlag(Qt.Sheet, True)
            self.setWindowModality(Qt.WindowModal)

        self._title = QLabel(title)
        self._title.setObjectName("dialogTitle")

        self.message = QLabel("")
        self.message.setObjectName("errorNote")
        self.message.setWordWrap(True)
        self.message.setVisible(False)

        self.create_button = QPushButton(commit_text)
        self.create_button.setObjectName("primary")
        self.create_button.setDefault(True)
        self.create_button.clicked.connect(self._on_create)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("ghost")
        self.cancel_button.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.setSpacing(SPACE_3)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.create_button)

        self.fields = QGridLayout()
        self.fields.setHorizontalSpacing(SPACE_3)
        self.fields.setVerticalSpacing(SPACE_2)
        self.fields.setColumnStretch(1, 1)

        divider = QFrame()
        divider.setObjectName("dialogDivider")
        divider.setFixedHeight(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACE_6, SPACE_6 - SPACE_1, SPACE_6, SPACE_4 + SPACE_1)
        outer.setSpacing(SPACE_4)
        outer.addWidget(self._title)
        outer.addLayout(self.fields)
        outer.addWidget(self.message)
        outer.addWidget(divider)
        outer.addLayout(buttons)

    def add_field(self, label: str, field: QWidget, hint: QWidget | None = None) -> None:
        """A labelled row, with an optional hint under the field."""
        row = self.fields.rowCount()
        name = _field_label(label)
        # A multi-line field reads from its first line, so its label does too.
        tall = isinstance(field, QTextEdit)
        name.setAlignment(Qt.AlignRight | (Qt.AlignTop if tall else Qt.AlignVCenter))
        if tall:
            name.setContentsMargins(0, SPACE_1 + 2, 0, 0)
        self.fields.addWidget(name, row, 0)
        self.fields.addWidget(field, row, 1)
        if hint is not None:
            self.fields.addWidget(hint, row + 1, 1)

    def _set_error(self, text: str) -> None:
        self.message.setText(text)
        self.message.setVisible(bool(text))

    def _on_create(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


class CreateProjectDialog(_BaseDialog):
    """Collects a single project name."""

    created = Signal(object)

    def __init__(self, store: TodoStore, parent: QWidget | None = None) -> None:
        super().__init__("New Project", store, parent)
        self.setMinimumWidth(440)

        self.name_edit = QLineEdit()
        self.name_edit.setValidator(NameValidator(self))
        self.name_edit.setMaxLength(NAME_MAX_LENGTH)
        self.name_edit.setPlaceholderText("Home Chores")
        self.name_edit.textChanged.connect(self._on_name_changed)
        self.name_edit.returnPressed.connect(self._on_create)

        self.hint = QLabel(NAME_HINT)
        self.hint.setObjectName("hint")

        self.add_field("Name", self.name_edit, self.hint)

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
        self.setMinimumWidth(440)
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

        self.add_field(field_label, self.name_edit, self.hint)

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
        super().__init__("New Task", store, parent)
        self.setMinimumWidth(480)

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
        self.date_edit = DatePicker()

        # -- project
        self.project_combo = MenuComboBox()
        self._load_projects(preselect_project_id)

        self.add_field("Name", self.name_edit, self.name_hint)
        self.add_field("Description", self.description_edit, self.description_hint)
        # A button and a combo box size themselves differently; pin both.
        for picker in (self.date_edit, self.project_combo):
            picker.setFixedHeight(FIELD_HEIGHT)
        self.add_field("Due", self.date_edit)
        self.add_field("Project", self.project_combo)

        self._revalidate()

    def _load_projects(self, preselect_project_id: int | None) -> None:
        self.project_combo.clear()
        projects = self.store.projects()
        for project in projects:
            self.project_combo.addItem(project.name, project.id)
        if not projects:
            self.project_combo.addItem("No projects yet — create one first", None)
            self.project_combo.setEnabled(False)
            return
        # The project used for the last task wins over the one in view: the
        # person asked to keep adding to the same project without re-picking
        # it. An archived or deleted one is not in the list, so it is skipped.
        for candidate in (self.store.last_task_project_id(), preselect_project_id):
            index = self.project_combo.findData(candidate) if candidate else -1
            if index >= 0:
                self.project_combo.setCurrentIndex(index)
                return

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


class MessageDialog(_BaseDialog):
    """A question or a notice, in the same sheet as every other dialog.

    Replaces QMessageBox, whose icon and native buttons broke the look. With
    *cancel_text* None it is a plain notice with a single button.
    """

    def __init__(
        self,
        title: str,
        message: str,
        parent: QWidget | None = None,
        *,
        confirm_text: str = "OK",
        cancel_text: str | None = "Cancel",
        destructive: bool = False,
    ) -> None:
        super().__init__(title, None, parent, commit_text=confirm_text)
        self.setMinimumWidth(400)
        self.text_label = QLabel(message)
        self.text_label.setObjectName("dialogMessage")
        self.text_label.setWordWrap(True)
        self.fields.addWidget(self.text_label, 0, 0, 1, 2)

        if cancel_text is None:
            self.cancel_button.setVisible(False)
        else:
            self.cancel_button.setText(cancel_text)
        if destructive:
            # Return should never delete: the safe choice is the default.
            self.create_button.setDefault(False)
            self.cancel_button.setDefault(True)

    def _on_create(self) -> None:
        self.accept()


def confirm(
    parent: QWidget | None,
    title: str,
    message: str,
    *,
    confirm_text: str,
    destructive: bool = False,
) -> bool:
    """Ask a yes/no question; True when the person confirmed."""
    dialog = MessageDialog(
        title, message, parent, confirm_text=confirm_text, destructive=destructive
    )
    return bool(dialog.exec())
