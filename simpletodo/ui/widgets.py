"""The two building blocks both tabs are made of."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    Qt,
    Signal,
)
from PySide6.QtGui import QCursor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..models import Task
from .style import CHECKBOX_SIZE, SPACE_1, SPACE_2, SPACE_3, SPACE_4, SPACE_6

MENU_GLYPH = "\u22ef"   # midline horizontal ellipsis


def _pointer_inside(widget: QWidget) -> bool:
    """Is the pointer still within *widget*?

    Qt sends a Leave event to a parent when the pointer moves onto one of its
    children, which would hide a hover-revealed control the instant you reach
    for it. This looks at the real cursor position instead.
    """
    return widget.rect().contains(widget.mapFromGlobal(QCursor.pos()))


def rounded_menu(parent: QWidget | None = None) -> QMenu:
    """A popup with rounded corners, the way a Mac menu looks.

    `border-radius` alone is not enough. A menu is its own top-level window, so
    the square corners outside the radius are filled with the window background
    and the rounding never shows. Making the window translucent and frameless
    lets the rounded shape in the stylesheet be what you actually see.
    """
    menu = QMenu(parent)
    menu.setWindowFlags(
        menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
    )
    menu.setAttribute(Qt.WA_TranslucentBackground)
    return menu


def svg_icon(svg: bytes, side: int) -> QIcon:
    """An icon drawn from SVG at 1x and 2x, so it is crisp on Retina too.

    Loading SVG through QIcon's file path would rasterise once at the file's
    own size and blur when scaled up.
    """
    renderer = QSvgRenderer(svg)
    icon = QIcon()
    for scale in (1, 2):
        pixmap = QPixmap(side * scale, side * scale)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(scale)
        icon.addPixmap(pixmap)
    return icon


class ClickableLabel(QLabel):
    """A label that reports clicks. QLabel has no clicked signal of its own."""

    clicked = Signal()

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt naming
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ElidedLabel(QLabel):
    """A one-line label that drops characters from the middle when squeezed.

    The status bar shares one row between the counts and a file path that can
    be longer than the minimum window is wide. Eliding the middle keeps both
    ends -- where the folder starts and the file name -- which are the parts
    that identify a path.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        # Without this the label's size hint is the full text, and the status
        # bar would rather clip the counts than shrink the path.
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def displayed_text(self) -> str:
        return self.fontMetrics().elidedText(
            self.text(), Qt.ElideMiddle, self.contentsRect().width()
        )

    def paintEvent(self, event):  # noqa: N802 - Qt naming
        # Painted by hand: QLabel placed right-aligned elided text a few pixels
        # off its own content rect, clipping the leading "/" of the path.
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(self.contentsRect(), self.alignment(), self.displayed_text())


def _menu_button(parent: QWidget | None = None) -> QPushButton:
    button = QPushButton(MENU_GLYPH, parent)
    button.setObjectName("rowMenu")
    button.setFixedSize(24, 20)
    button.setCursor(Qt.PointingHandCursor)
    button.setFocusPolicy(Qt.NoFocus)
    button.setToolTip("More actions")
    button.setProperty("revealed", False)
    return button


ARROW_OPEN = "▼"    # down-pointing triangle
ARROW_SHUT = "▶"    # right-pointing triangle

#: Long enough to read as motion, short enough not to be in the way.
ANIMATION_MS = 170


class _HeadingButton(QPushButton):
    """A button that sizes itself to the layout inside it.

    QPushButton derives its size hint from its text. The heading's text lives
    in child labels instead, so without this the button collapses to a few
    pixels and clips them.
    """

    hoverChanged = Signal(bool)

    def enterEvent(self, event):  # noqa: N802 - Qt naming
        self.hoverChanged.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802 - Qt naming
        if not _pointer_inside(self):
            self.hoverChanged.emit(False)
        super().leaveEvent(event)

    def sizeHint(self):  # noqa: N802 - Qt naming
        layout = self.layout()
        return layout.sizeHint() if layout is not None else super().sizeHint()

    def minimumSizeHint(self):  # noqa: N802 - Qt naming
        layout = self.layout()
        return layout.minimumSize() if layout is not None else super().minimumSizeHint()


class CollapsibleSection(QWidget):
    """A heading that reveals its body with a slide.

    The heading is one button holding three labels, so the title and its count
    can differ in size and weight. The labels ignore the mouse, which leaves
    the whole heading clickable and keyboard-focusable as a single control.
    """

    toggled = Signal(bool)
    #: Someone asked for this section's menu, at a global position.
    menuRequested = Signal(QPoint)

    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
        *,
        with_menu: bool = False,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._with_menu = with_menu
        self._count_text = ""
        self._expanded = False

        self.header = _HeadingButton()
        self.header.setObjectName("sectionHeader")
        # Fixed height: a heading is exactly as tall as its content and must
        # never be compressed to fit, or a long list squashes every row.
        self.header.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.setFocusPolicy(Qt.TabFocus)
        self.header.clicked.connect(self.toggle)

        self._arrow = QLabel(ARROW_SHUT)
        self._arrow.setObjectName("sectionArrow")
        self._arrow.setFixedWidth(SPACE_3)
        self._title_label = QLabel(title)
        self._title_label.setObjectName("sectionTitle")
        self._count_label = QLabel("")
        self._count_label.setObjectName("sectionCount")
        for label in (self._arrow, self._title_label, self._count_label):
            label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.menu_button = _menu_button()
        self.menu_button.setVisible(with_menu)
        self.menu_button.clicked.connect(self._request_menu_at_button)
        if with_menu:
            self.header.hoverChanged.connect(self._reveal_menu)

        heading = QHBoxLayout(self.header)
        heading.setContentsMargins(SPACE_1, SPACE_3, SPACE_1, SPACE_3)
        heading.setSpacing(SPACE_2)
        heading.addWidget(self._arrow)
        heading.addWidget(self._title_label)
        heading.addWidget(self._count_label)
        heading.addStretch(1)
        heading.addWidget(self.menu_button)

        self.body = QWidget()
        self.body.setObjectName("sectionBody")
        self._body_layout = QVBoxLayout(self.body)
        self._body_layout.setContentsMargins(0, SPACE_2, 0, SPACE_2)
        self._body_layout.setSpacing(SPACE_1)

        # Animating maximumHeight keeps the slide cheap and flicker-free.
        self.body.setMaximumHeight(0)
        self.body.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        self._anim = QPropertyAnimation(self.body, b"maximumHeight", self)
        self._anim.setDuration(ANIMATION_MS)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._anim.finished.connect(self._on_anim_finished)

        # Likewise the section as a whole: its height is its content's height.
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.header)
        outer.addWidget(self.body)

    # -- content --------------------------------------------------------

    @property
    def content_layout(self) -> QVBoxLayout:
        return self._body_layout

    def clear(self) -> None:
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def add_row(self, widget: QWidget) -> None:
        self._body_layout.addWidget(widget)

    def set_counts(self, done: int, total: int) -> None:
        self._count_text = f"({done}/{total})"
        self._refresh_header()

    def set_title(self, title: str) -> None:
        self._title = title
        self._refresh_header()

    @property
    def header_text(self) -> str:
        """The heading as one string: arrow, title, count."""
        parts = [self._arrow.text(), self._title_label.text()]
        if self._count_label.text():
            parts.append(self._count_label.text())
        return "  ".join(parts)

    def _refresh_header(self) -> None:
        self._arrow.setText(ARROW_OPEN if self._expanded else ARROW_SHUT)
        self._title_label.setText(self._title)
        self._count_label.setText(self._count_text)

    # -- menu -----------------------------------------------------------

    def _reveal_menu(self, revealed: bool) -> None:
        self.menu_button.setProperty("revealed", revealed)
        restyle(self.menu_button)

    def _request_menu_at_button(self) -> None:
        corner = self.menu_button.mapToGlobal(
            QPoint(0, self.menu_button.height())
        )
        self.menuRequested.emit(corner)

    def contextMenuEvent(self, event):  # noqa: N802 - Qt naming
        if self._with_menu:
            self.menuRequested.emit(event.globalPos())
            event.accept()
        else:
            super().contextMenuEvent(event)

    # -- open / shut ----------------------------------------------------

    @property
    def expanded(self) -> bool:
        return self._expanded

    def toggle(self) -> None:
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool, *, animate: bool = True) -> None:
        if expanded == self._expanded:
            return
        self._expanded = expanded
        self._refresh_header()

        target = self._natural_height() if expanded else 0
        self._anim.stop()
        if not animate:
            self.body.setMaximumHeight(target)
            self._on_anim_finished()
            self._propagate()
        else:
            self._anim.setStartValue(self.body.maximumHeight())
            self._anim.setEndValue(target)
            self._anim.start()
        self.toggled.emit(expanded)

    def refit(self) -> None:
        """Re-measure an open body after its rows changed."""
        if self._expanded and self._anim.state() != QPropertyAnimation.Running:
            self.body.setMaximumHeight(self._natural_height())

    def _natural_height(self) -> int:
        self.body.layout().activate()
        return max(self.body.sizeHint().height(), 1)

    def _on_anim_finished(self) -> None:
        if self._expanded:
            # Release the cap so the body can grow with its content.
            self.body.setMaximumHeight(16_777_215)
        self._propagate()

    def _propagate(self) -> None:
        """Tell the ancestors our preferred height changed."""
        self.body.updateGeometry()
        self.updateGeometry()
        parent = self.parentWidget()
        while parent is not None:
            layout = parent.layout()
            if layout is not None:
                layout.invalidate()
                # activate() as well, so a scroll area shrinks its widget back
                # when a section closes and the list re-centres.
                layout.activate()
            parent.updateGeometry()
            parent = parent.parentWidget()


class TaskRow(QFrame):
    """One task: a checkbox, its name, and a line of quiet metadata."""

    toggled = Signal(int, bool)        # task id, now-completed
    #: Someone asked for this task's menu, at a global position.
    menuRequested = Signal(QPoint)
    #: The description was revealed or hidden; the row's height changed.
    descriptionToggled = Signal(bool)

    def __init__(
        self,
        task: Task,
        *,
        show_project: bool = False,
        today: date | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("taskRow")
        self.task = task

        # The checkbox carries no label: its text used to be the task name, so
        # clicking the name toggled completion. Ticking the box is now the only
        # way to complete a task, and the name is free to do something else.
        self.check = QCheckBox()
        self.check.setObjectName("taskCheck")
        self.check.setCursor(Qt.PointingHandCursor)
        self.check.setChecked(task.is_completed)
        self.check.setProperty("done", task.is_completed)
        self.check.setAccessibleName(task.name)
        self.check.setToolTip("Complete this task")
        self.check.toggled.connect(self._on_toggled)

        self.name_label = ClickableLabel(task.name)
        self.name_label.setObjectName("taskName")
        self.name_label.setProperty("done", task.is_completed)
        self.name_label.setProperty("expandable", bool(task.description))
        if task.description:
            self.name_label.setCursor(Qt.PointingHandCursor)
            self.name_label.setToolTip("Show the description")
        self.name_label.clicked.connect(self.toggle_description)

        today = today or date.today()

        # The project and the due note are separate labels so that only the
        # due note turns red when a task is late.
        self._show_project = show_project
        self.project_label = QLabel(task.project_name)
        self.project_label.setObjectName("taskMeta")
        self.project_label.setVisible(show_project)

        self.due_label = QLabel(self._due_text(show_project, today))
        self.due_label.setObjectName("taskMeta")
        self.due_label.setProperty("overdue", task.is_overdue(today))
        self.due_label.setVisible(bool(self.due_label.text()))

        self.menu_button = _menu_button()
        self.menu_button.clicked.connect(self._request_menu_at_button)

        # The hover tint belongs to the task line, not to a revealed
        # description hanging below it.
        self.line = QWidget()
        self.line.setObjectName("taskLine")
        row = QHBoxLayout(self.line)
        # Indented past the heading so tasks read as nested under it.
        row.setContentsMargins(SPACE_6, SPACE_1, SPACE_2, SPACE_1)
        row.setSpacing(SPACE_3)
        row.addWidget(self.check)
        row.addWidget(self.name_label)
        row.addStretch(1)
        row.addWidget(self.project_label)
        row.addWidget(self.due_label)
        # Always in the layout, invisible until hover: revealing it by showing
        # the widget would shift the labels beside it every time.
        row.addWidget(self.menu_button)

        self.description_label = QLabel(task.description)
        self.description_label.setObjectName("taskDescription")
        self.description_label.setWordWrap(True)

        self.description_panel = QWidget()
        self.description_panel.setObjectName("taskDescriptionPanel")
        panel = QVBoxLayout(self.description_panel)
        # Indented to sit under the task name, not under the checkbox.
        panel.setContentsMargins(
            SPACE_6 + CHECKBOX_SIZE + SPACE_3, 0, SPACE_4, SPACE_2
        )
        panel.setSpacing(0)
        panel.addWidget(self.description_label)
        self.description_panel.setMaximumHeight(0)
        self.description_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        self._description_anim = QPropertyAnimation(
            self.description_panel, b"maximumHeight", self
        )
        self._description_anim.setDuration(ANIMATION_MS)
        self._description_anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._description_anim.finished.connect(self._on_description_settled)
        self._description_shown = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.line)
        outer.addWidget(self.description_panel)

    # -- description ----------------------------------------------------

    @property
    def description_shown(self) -> bool:
        return self._description_shown

    def toggle_description(self) -> None:
        """Show or hide the description. A task without one does nothing."""
        if not self.task.description:
            return
        self.set_description_shown(not self._description_shown)

    def set_description_shown(self, shown: bool, *, animate: bool = True) -> None:
        if shown == self._description_shown or not self.task.description:
            return
        self._description_shown = shown

        self.description_panel.layout().activate()
        target = self.description_panel.sizeHint().height() if shown else 0
        self._description_anim.stop()
        if animate:
            self._description_anim.setStartValue(
                self.description_panel.maximumHeight()
            )
            self._description_anim.setEndValue(target)
            self._description_anim.start()
        else:
            self.description_panel.setMaximumHeight(target)
            self._on_description_settled()

    def _on_description_settled(self) -> None:
        if self._description_shown:
            self.description_panel.setMaximumHeight(16_777_215)
        self.updateGeometry()
        self.descriptionToggled.emit(self._description_shown)

    @property
    def meta_text(self) -> str:
        """Everything shown to the right of the task name.

        Reads the flags rather than isVisible(), which stays False until the
        window is first shown.
        """
        parts = [
            self.project_label.text() if self._show_project else "",
            self.due_label.text(),
        ]
        return "   ".join(part for part in parts if part)

    def _due_text(self, show_project: bool, today: date) -> str:
        if self.task.is_overdue(today):
            days = (today - self.task.due).days
            return f"overdue {days}d" if days > 1 else "overdue"
        if not show_project:
            return self.task.due.strftime("%d %b")
        return ""

    def _on_toggled(self, checked: bool) -> None:
        if self.task.id is not None:
            self.toggled.emit(self.task.id, checked)

    # -- menu -----------------------------------------------------------

    def _reveal_menu(self, revealed: bool) -> None:
        self.menu_button.setProperty("revealed", revealed)
        restyle(self.menu_button)

    def _request_menu_at_button(self) -> None:
        corner = self.menu_button.mapToGlobal(QPoint(0, self.menu_button.height()))
        self.menuRequested.emit(corner)

    def enterEvent(self, event):  # noqa: N802 - Qt naming
        self._reveal_menu(True)
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802 - Qt naming
        if not _pointer_inside(self):
            self._reveal_menu(False)
        super().leaveEvent(event)

    def contextMenuEvent(self, event):  # noqa: N802 - Qt naming
        self.menuRequested.emit(event.globalPos())
        event.accept()


def restyle(widget: QWidget) -> None:
    """Re-apply the stylesheet after a dynamic property changed."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
