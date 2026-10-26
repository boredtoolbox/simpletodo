"""The building blocks of the sidebar and the task pane."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import (
    QDate,
    QEasingCurve,
    QLocale,
    QPoint,
    QPropertyAnimation,
    Qt,
    Signal,
)
from PySide6.QtGui import QCursor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..models import Task
from .style import (
    CHECKBOX_SIZE,
    CHEVRON_URL,
    DAY_CELL,
    ITEM_PADDING,
    SPACE_1,
    SPACE_2,
    SPACE_3,
    SPACE_4,
)

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


class TopBar(QWidget):
    """A strip that behaves like a title bar: drag to move, double-click to zoom.

    On macOS the content runs up under a transparent title bar, so this strip
    is where the traffic lights sit, and its empty parts are all there is to
    grab the window by. Buttons inside it take their own clicks first.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("topBar")

    def mousePressEvent(self, event):  # noqa: N802 - Qt naming
        handle = self.window().windowHandle()
        if event.button() == Qt.LeftButton and handle is not None:
            handle.startSystemMove()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):  # noqa: N802 - Qt naming
        if event.button() == Qt.LeftButton:
            window = self.window()
            window.showNormal() if window.isMaximized() else window.showMaximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


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
    """A one-line label that drops characters when squeezed.

    The status bar shares one row between the counts and a file path that can
    be longer than the minimum window is wide. Eliding the middle, the
    default, keeps both ends -- where the folder starts and the file name --
    which are the parts that identify a path. Sidebar text elides at the end.
    """

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
        *,
        elide: Qt.TextElideMode = Qt.ElideMiddle,
    ) -> None:
        super().__init__(text, parent)
        self._elide = elide
        # Without this the label's size hint is the full text, and the status
        # bar would rather clip the counts than shrink the path.
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def displayed_text(self) -> str:
        return self.fontMetrics().elidedText(
            self.text(), self._elide, self.contentsRect().width()
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


#: Long enough to read as motion, short enough not to be in the way.
ANIMATION_MS = 170


class SidebarItem(QFrame):
    """One entry in the sidebar: a bold title over a two-tone second line.

    Laid out like a note in the Notes list -- the second line leads with a
    dark fact (the X/Y count) and trails off into a muted preview, the next
    task still to do.
    """

    #: Pressed: select me.
    chosen = Signal(object)
    #: Someone asked for this item's menu, at a global position.
    menuRequested = Signal(QPoint)

    def __init__(
        self,
        key: object,
        title: str,
        *,
        with_menu: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("sidebarItem")
        self.setProperty("selected", False)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.key = key
        self._with_menu = with_menu

        self.title_label = ElidedLabel(title, elide=Qt.ElideRight)
        self.title_label.setObjectName("itemTitle")
        self.title_label.setToolTip(title)
        self.strong_label = QLabel("")
        self.strong_label.setObjectName("itemStrong")
        self.soft_label = ElidedLabel("", elide=Qt.ElideRight)
        self.soft_label.setObjectName("itemSoft")
        for label in (self.title_label, self.strong_label, self.soft_label):
            label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.menu_button = _menu_button()
        self.menu_button.setVisible(with_menu)
        self.menu_button.clicked.connect(self._request_menu_at_button)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(SPACE_1)
        top.addWidget(self.title_label, 1)
        top.addWidget(self.menu_button)

        second = QHBoxLayout()
        second.setContentsMargins(0, 0, 0, 0)
        second.setSpacing(SPACE_2)
        second.addWidget(self.strong_label)
        second.addWidget(self.soft_label, 1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(ITEM_PADDING, SPACE_2 + 2, SPACE_2, SPACE_2 + 2)
        outer.setSpacing(2)
        outer.addLayout(top)
        outer.addLayout(second)

    @property
    def title(self) -> str:
        return self.title_label.text()

    @property
    def detail_text(self) -> str:
        """The second line as one string."""
        return "  ".join(t for t in (self.strong_label.text(), self.soft_label.text()) if t)

    def set_detail(self, strong: str, soft: str) -> None:
        self.strong_label.setText(strong)
        self.soft_label.setText(soft)

    @property
    def selected(self) -> bool:
        return bool(self.property("selected"))

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        restyle(self)

    def mousePressEvent(self, event):  # noqa: N802 - Qt naming
        # On press, as Notes does: selection should feel immediate.
        if event.button() == Qt.LeftButton:
            self.chosen.emit(self.key)
            event.accept()
            return
        super().mousePressEvent(event)

    # -- menu -----------------------------------------------------------

    def _reveal_menu(self, revealed: bool) -> None:
        self.menu_button.setProperty("revealed", revealed)
        restyle(self.menu_button)

    def _request_menu_at_button(self) -> None:
        corner = self.menu_button.mapToGlobal(QPoint(0, self.menu_button.height()))
        self.menuRequested.emit(corner)

    def enterEvent(self, event):  # noqa: N802 - Qt naming
        if self._with_menu:
            self._reveal_menu(True)
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802 - Qt naming
        if self._with_menu and not _pointer_inside(self):
            self._reveal_menu(False)
        super().leaveEvent(event)

    def contextMenuEvent(self, event):  # noqa: N802 - Qt naming
        if self._with_menu:
            self.menuRequested.emit(event.globalPos())
            event.accept()
        else:
            super().contextMenuEvent(event)


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
        # A row is exactly as tall as its content: in a long list the pane
        # scrolls rather than squeezing every row to its minimum.
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
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
        row.setContentsMargins(SPACE_2, SPACE_1, SPACE_2, SPACE_1)
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
            SPACE_2 + CHECKBOX_SIZE + SPACE_3, 0, SPACE_4, SPACE_2
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

    def set_completed(self, done: bool, *, today: date | None = None) -> None:
        """Show the task as done or not, without rebuilding the row."""
        self.task.is_completed = done
        # Silent: this mirrors a change already stored, and re-emitting it
        # would write it again.
        blocked = self.check.blockSignals(True)
        self.check.setChecked(done)
        self.check.blockSignals(blocked)

        # A finished task is never overdue, so the due note can change too.
        today = today or date.today()
        self.due_label.setText(self._due_text(self._show_project, today))
        self.due_label.setProperty("overdue", self.task.is_overdue(today))
        self.due_label.setVisible(bool(self.due_label.text()))

        self.check.setProperty("done", done)
        self.name_label.setProperty("done", done)
        for widget in (self.check, self.name_label, self.due_label):
            restyle(widget)

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


def settle_scroll(scroll: QScrollArea) -> None:
    """Fit a resizable scroll area's widget to its content, now.

    QScrollArea refits its widget only on a deferred LayoutRequest, and a
    layout ignores children that are not yet visible -- Qt shows freshly
    added ones on the next event-loop turn. After a burst of rebuilds the
    widget kept the viewport's height and every row was squashed to a
    sliver. Showing the children and applying the fit synchronously avoids
    both; see test_a_long_task_list_scrolls_instead_of_squashing.
    """
    holder = scroll.widget()
    if holder is None or holder.layout() is None:
        return
    for child in holder.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
        if not child.testAttribute(Qt.WA_WState_ExplicitShowHide):
            child.show()
    holder.layout().invalidate()
    holder.layout().activate()
    viewport = scroll.viewport()
    wanted = max(viewport.height(), holder.sizeHint().height())
    if holder.height() != wanted:
        holder.resize(viewport.width(), wanted)


def restyle(widget: QWidget) -> None:
    """Re-apply the stylesheet after a dynamic property changed."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


# -- pickers: pop-ups that look like the app's menus --------------------


class MenuComboBox(QComboBox):
    """A combo box whose list opens as one of the app's rounded menus.

    Qt's own popup is a square list box; a Mac pop-up button shows a menu,
    and this one matches the Move to submenu, with a tick on the current
    choice. Opened with popup(), never exec(), like every menu here.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.menu: QMenu | None = None

    def showPopup(self):  # noqa: N802 - Qt naming
        menu = rounded_menu(self)
        menu.setAttribute(Qt.WA_DeleteOnClose)
        menu.setMinimumWidth(self.width())
        current = None
        for index in range(self.count()):
            action = menu.addAction(self.itemText(index))
            action.setCheckable(True)
            action.setChecked(index == self.currentIndex())
            action.triggered.connect(lambda _=False, i=index: self.setCurrentIndex(i))
            if index == self.currentIndex():
                current = action
        menu.popup(self.mapToGlobal(QPoint(0, self.height() + SPACE_1)))
        if current is not None:
            menu.setActiveAction(current)
        self.menu = menu

    def hidePopup(self):  # noqa: N802 - Qt naming
        if self.menu is not None and self.menu.isVisible():
            self.menu.close()


#: How the due date reads in its field: short, with the weekday, since the
#: weekday is what people plan by.
DATE_FIELD_FORMAT = "ddd d MMM yyyy"


class DatePicker(QPushButton):
    """A date field that opens a DatePopup. Same API as QDateEdit's core.

    QDateEdit's calendar popup is a grey, square, spreadsheet-like grid;
    this shows the app's own rounded picker instead.
    """

    dateChanged = Signal(QDate)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dateField")
        self._date = QDate.currentDate()
        self.popup: DatePopup | None = None

        # The chevron is a child so the text keeps the field's left edge.
        chevron = QLabel()
        chevron.setObjectName("fieldChevron")
        chevron.setPixmap(QIcon(CHEVRON_URL).pixmap(10, 10))
        chevron.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, SPACE_2 + 1, 0)
        row.addStretch(1)
        row.addWidget(chevron)

        self.clicked.connect(self.open_popup)
        self._show_date()

    def date(self) -> QDate:
        return self._date

    def setDate(self, value: QDate) -> None:  # noqa: N802 - mirrors QDateEdit
        if value.isValid() and value != self._date:
            self._date = value
            self._show_date()
            self.dateChanged.emit(value)

    def _show_date(self) -> None:
        self.setText(self._date.toString(DATE_FIELD_FORMAT))

    def open_popup(self) -> "DatePopup":
        popup = DatePopup(self._date, self)
        popup.chosen.connect(self.setDate)
        popup.show_below(self)
        self.popup = popup
        return popup

    def keyPressEvent(self, event):  # noqa: N802 - Qt naming
        # Alt+Down and F4 open a combo box; a date field should do the same.
        if event.key() == Qt.Key_F4 or (
            event.key() == Qt.Key_Down and event.modifiers() & Qt.AltModifier
        ):
            self.open_popup()
            event.accept()
            return
        super().keyPressEvent(event)


class _QuickPick(QPushButton):
    """A menu-style row: a label on the left, a muted date on the right."""

    def __init__(self, label: str, detail: str, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.setObjectName("popupItem")
        self.setFocusPolicy(Qt.NoFocus)
        meta = QLabel(detail)
        meta.setObjectName("popupItemMeta")
        meta.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, SPACE_4, 0)
        row.addStretch(1)
        row.addWidget(meta)


class DatePopup(QWidget):
    """A rounded month picker, styled like the app's menus.

    Quick picks sit at the top as menu rows; below them a month grid with
    round day cells. Arrows move a cursor, Page Up/Down change month, Return
    picks, Esc closes. It is a Qt.Popup, so a click outside dismisses it.
    """

    chosen = Signal(QDate)

    QUICK_PICKS = (("Today", 0), ("Tomorrow", 1), ("Next week", 7))

    def __init__(self, selected: QDate, parent: QWidget | None = None) -> None:
        super().__init__(
            parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        )
        # Rounded only because the window itself is see-through; the same
        # reason rounded_menu() does this.
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setObjectName("datePopup")
        self.setFocusPolicy(Qt.StrongFocus)

        self.selected = selected
        self.cursor = selected
        self.month = QDate(selected.year(), selected.month(), 1)
        today = QDate.currentDate()

        panel = QFrame()
        panel.setObjectName("popupPanel")
        body = QVBoxLayout(panel)
        body.setContentsMargins(SPACE_1, SPACE_1, SPACE_1, SPACE_2)
        body.setSpacing(0)

        self.quick_picks: dict[str, QPushButton] = {}
        for label, days in self.QUICK_PICKS:
            day = today.addDays(days)
            button = _QuickPick(label, day.toString("ddd d MMM"))
            button.clicked.connect(lambda _=False, d=day: self.choose(d))
            self.quick_picks[label] = button
            body.addWidget(button)

        divider = QFrame()
        divider.setObjectName("popupDivider")
        divider.setFixedHeight(1)
        body.addSpacing(SPACE_1)
        body.addWidget(divider)
        body.addSpacing(SPACE_2)

        self.title = QLabel()
        self.title.setObjectName("calTitle")
        self.prev_button = self._nav("‹", "Previous month", -1)
        self.next_button = self._nav("›", "Next month", 1)
        header = QHBoxLayout()
        header.setContentsMargins(SPACE_3, 0, SPACE_1, SPACE_1)
        header.addWidget(self.title, 1)
        header.addWidget(self.prev_button)
        header.addWidget(self.next_button)
        body.addLayout(header)

        grid = QGridLayout()
        grid.setContentsMargins(SPACE_2, 0, SPACE_2, 0)
        grid.setHorizontalSpacing(2)
        grid.setVerticalSpacing(2)
        first = QLocale().firstDayOfWeek().value       # 1 = Monday ... 7 = Sunday
        self._weekdays = [((first - 1 + i) % 7) + 1 for i in range(7)]
        for column, weekday in enumerate(self._weekdays):
            name = QLocale().dayName(weekday, QLocale.NarrowFormat)
            label = QLabel(name)
            label.setObjectName("calWeekday")
            label.setAlignment(Qt.AlignCenter)
            grid.addWidget(label, 0, column)
        self.cells: list[QPushButton] = []
        for index in range(42):
            cell = QPushButton()
            cell.setObjectName("calDay")
            cell.setFixedSize(DAY_CELL, DAY_CELL)
            cell.setFocusPolicy(Qt.NoFocus)
            cell.clicked.connect(lambda _=False, i=index: self.choose(self._cell_dates[i]))
            self.cells.append(cell)
            grid.addWidget(cell, 1 + index // 7, index % 7)
        body.addLayout(grid)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(panel)

        self._cell_dates: list[QDate] = []
        self._today = today
        self._refresh()

    def _nav(self, glyph: str, tip: str, step: int) -> QPushButton:
        button = QPushButton(glyph)
        button.setObjectName("calNav")
        button.setFixedSize(DAY_CELL - 4, DAY_CELL - 4)
        button.setToolTip(tip)
        button.setFocusPolicy(Qt.NoFocus)
        button.clicked.connect(lambda: self.show_month(self.month.addMonths(step)))
        return button

    # -- showing --------------------------------------------------------

    def show_below(self, anchor: QWidget) -> None:
        """Open under *anchor*, or above it when there is no room below."""
        self.adjustSize()
        below = anchor.mapToGlobal(QPoint(0, anchor.height() + SPACE_1))
        screen = anchor.screen().availableGeometry()
        if below.y() + self.height() > screen.bottom():
            below = anchor.mapToGlobal(QPoint(0, -self.height() - SPACE_1))
        self.move(below)
        self.show()
        self.setFocus(Qt.PopupFocusReason)

    def show_month(self, month: QDate) -> None:
        self.month = QDate(month.year(), month.month(), 1)
        if (self.cursor.year(), self.cursor.month()) != (month.year(), month.month()):
            self.cursor = self.month.addDays(min(self.cursor.day(), self.month.daysInMonth()) - 1)
        self._refresh()

    def _refresh(self) -> None:
        self.title.setText(self.month.toString("MMMM yyyy"))
        lead = self._weekdays.index(self.month.dayOfWeek())
        start = self.month.addDays(-lead)
        self._cell_dates = [start.addDays(i) for i in range(42)]
        for cell, day in zip(self.cells, self._cell_dates):
            cell.setText(str(day.day()))
            cell.setProperty("outside", day.month() != self.month.month())
            cell.setProperty("today", day == self._today)
            # Not "cursor": that name is QWidget's own mouse-cursor property.
            cell.setProperty("keyed", day == self.cursor)
            cell.setProperty("selected", day == self.selected)
            cell.setAccessibleName(day.toString("dddd d MMMM yyyy"))
            restyle(cell)

    def cell_for(self, day: QDate) -> QPushButton | None:
        """The cell showing *day*, if it is on the page."""
        if day in self._cell_dates:
            return self.cells[self._cell_dates.index(day)]
        return None

    # -- choosing -------------------------------------------------------

    def choose(self, day: QDate) -> None:
        self.chosen.emit(day)
        self.close()

    def keyPressEvent(self, event):  # noqa: N802 - Qt naming
        steps = {Qt.Key_Left: -1, Qt.Key_Right: 1, Qt.Key_Up: -7, Qt.Key_Down: 7}
        key = event.key()
        if key in steps:
            self._move_cursor(self.cursor.addDays(steps[key]))
        elif key == Qt.Key_PageUp:
            self._move_cursor(self.cursor.addMonths(-1))
        elif key == Qt.Key_PageDown:
            self._move_cursor(self.cursor.addMonths(1))
        elif key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.choose(self.cursor)
        elif key == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def _move_cursor(self, day: QDate) -> None:
        self.cursor = day
        self.month = QDate(day.year(), day.month(), 1)
        self._refresh()
