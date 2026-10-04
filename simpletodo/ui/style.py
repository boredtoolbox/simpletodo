"""One stylesheet for the whole application.

A modern-minimalist system: near-black text on off-white, a single blue accent,
hierarchy carried by size and weight rather than decoration. Radii, borders and
motion are used sparingly and only where they do work.
"""

from __future__ import annotations

from pathlib import Path

#: Qt stylesheets need a real path for url(); resolve it next to this module.
_ASSETS = Path(__file__).resolve().parent / "assets"
CHECK_URL = _ASSETS.joinpath("check.svg").as_posix()
PAPER_URL = _ASSETS.joinpath("paper.png").as_posix()

#: Width of the centred content column.
CONTENT_WIDTH = 560

# -- colour -------------------------------------------------------------

# Unruled paper: a warm off-white, never pure white, carrying a faint grain
# from assets/paper.png. The greys below are warmed to match -- neutral greys
# read as dirty against a cream ground.
PAPER = "#FAF7F0"          # the paper itself (flat fallback under the grain)
PAPER_RAISED = "#FFFDF8"   # inputs and menus, a shade lighter than the sheet
HOVER = "#F2EDE1"          # the only hover treatment

INK = "#1A1A1A"            # primary text, never pure black
INK_SOFT = "#6B6558"       # secondary text
INK_FAINT = "#9C958A"      # tertiary text, placeholders

LINE = "#E6DECF"           # borders and dividers
INK_MARK = "#2B2722"       # what the app stamps on the paper: ticks, marks
ACCENT = "#2563EB"         # the single accent
ACCENT_PRESSED = "#1D4ED8"
DANGER = "#DC2626"         # overdue only

# -- spacing ------------------------------------------------------------

#: The 4px grid every margin and padding in the app snaps to.
SPACE_1, SPACE_2, SPACE_3, SPACE_4, SPACE_6 = 4, 8, 12, 16, 24

#: Breathing room between one section and the next.
SECTION_GAP = SPACE_6

# -- type ---------------------------------------------------------------

#: The one face the application is set in, best first. American Typewriter is
#: the macOS classic; the Courier family and the Linux monospaces follow. Only
#: families actually installed are ever named in the stylesheet: listing a
#: missing one makes Qt scan its alias table, which costs ~140ms at startup.
TYPEWRITER_FAMILIES = (
    "American Typewriter",
    "Courier Prime",
    "Courier New",
    "Courier",
    "Nimbus Mono PS",
    "Liberation Mono",
    "DejaVu Sans Mono",
    "Andale Mono",
    "Menlo",
    "Monaco",
)

#: Corner radii for popup menus, in the macOS idiom.
MENU_RADIUS = 10
MENU_ITEM_RADIUS = 5

#: Side of the checkbox indicator. Shared so the description below a task can
#: line up with the task name rather than with the checkbox.
CHECKBOX_SIZE = 16

TEXT_TITLE = 23              # the masthead
TEXT_HEADING = 16            # section titles
TEXT_BODY = 13               # task names, inputs
TEXT_META = 12               # counts, dates, hints


#: The archive button's glyph: a lidded box, drawn as line art so it sits
#: beside the + without outweighing it. Kept here, not in assets/, because its
#: ink comes from the tokens above.
_ARCHIVE_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20">
  <g fill="none" stroke="{ink}" stroke-width="1.4"
     stroke-linecap="round" stroke-linejoin="round">
    <rect x="2.5" y="4" width="15" height="4" rx="1"/>
    <path d="M4 8 V15.5 A1 1 0 0 0 5 16.5 H15 A1 1 0 0 0 16 15.5 V8"/>
    <path d="M8 11.25 H12"/>
  </g>
</svg>
"""


def archive_icon_svg(ink: str = INK_SOFT) -> bytes:
    return _ARCHIVE_SVG.format(ink=ink).encode()


def resolve_typewriter_family() -> str:
    """The first typewriter face installed here, else any monospace Qt has.

    Requires a QApplication to exist, so call it after one is constructed.
    """
    from PySide6.QtGui import QFont, QFontDatabase

    installed = set(QFontDatabase.families())
    for family in TYPEWRITER_FAMILIES:
        if family in installed:
            return family
    fallback = QFont()
    fallback.setStyleHint(QFont.TypeWriter)
    return fallback.defaultFamily()


def stylesheet(font_family: str | None = None) -> str:
    """The application stylesheet, bound to a font family that exists."""
    family = font_family or resolve_typewriter_family()
    return _TEMPLATE.replace("__FONT_FAMILY__", family)


_TEMPLATE = f"""
QWidget {{
    background: {PAPER};
    color: {INK};
    font-family: "__FONT_FAMILY__";
    font-size: {TEXT_BODY}px;
    font-weight: 400;
}}

/* The sheet of paper. Only these two carry the grain: every container inside
   them is transparent, so the tile never restarts partway across the window. */
QWidget#appBackdrop, QDialog {{
    /* The shorthand is deliberate: `background-image` with a separate
       `background-repeat` paints a single tile at the origin in this Qt, while
       the shorthand tiles across the whole widget. */
    background: {PAPER} url("{PAPER_URL}") repeat;
}}
QTabWidget, QTabWidget > QWidget, QStackedWidget,
QWidget#tabPage, QScrollArea, QScrollArea > QWidget > QWidget,
QWidget#scrollHolder, QWidget#contentColumn, QWidget#sectionBody {{
    background: transparent;
}}

/* ---- the masthead ---- */
QLabel#appTitle {{
    font-size: {TEXT_TITLE}px;
    font-weight: 700;
    color: {INK};
    background: transparent;
    letter-spacing: 1px;
}}

/* ---- tabs: quiet navigation, not chrome ---- */
QTabWidget::pane {{
    border: none;
    background: transparent;
}}
QTabBar {{
    qproperty-drawBase: 0;
    background: transparent;
}}
QTabBar::tab {{
    background: transparent;
    color: {INK_FAINT};
    padding: {SPACE_2}px {SPACE_4}px;
    margin: 0;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: {TEXT_BODY}px;
    font-weight: 500;
}}
QTabBar::tab:hover {{
    color: {INK_SOFT};
}}
QTabBar::tab:selected {{
    color: {INK};
    border-bottom: 2px solid {ACCENT};
}}

/* ---- section headings ---- */
QPushButton#sectionHeader {{
    background: transparent;
    border: none;
    border-bottom: 1px solid {LINE};
    padding: 0;
    text-align: left;
}}
QLabel#sectionArrow {{
    color: {INK_FAINT};
    font-size: 10px;
    background: transparent;
}}
QPushButton#sectionHeader:hover QLabel#sectionArrow {{
    color: {INK_SOFT};
}}
QLabel#sectionTitle {{
    color: {INK};
    font-size: {TEXT_HEADING}px;
    font-weight: 600;
    background: transparent;
}}
QLabel#sectionCount {{
    color: {INK_SOFT};
    font-size: {TEXT_META}px;
    font-weight: 400;
    background: transparent;
}}

/* ---- task rows ---- */
QWidget#taskRow {{
    background: transparent;
}}
QWidget#taskLine {{
    background: transparent;
}}
QWidget#taskLine:hover {{
    background: {HOVER};
}}

QLabel#taskName {{
    color: {INK};
    font-size: {TEXT_BODY}px;
    background: transparent;
}}
QLabel#taskName[done="true"] {{
    color: {INK_FAINT};
}}
/* Only a task that has something to show invites a click. */
QLabel#taskName[expandable="true"]:hover {{
    color: {ACCENT};
}}

QWidget#taskDescriptionPanel {{
    background: transparent;
}}
QLabel#taskDescription {{
    color: {INK_SOFT};
    font-size: {TEXT_META}px;
    background: transparent;
}}

QCheckBox#taskCheck {{
    /* No label of its own, so no gap to reserve for one. */
    spacing: 0;
    padding: {SPACE_1}px 0;
    font-size: {TEXT_BODY}px;
    color: {INK};
    background: transparent;
}}
QCheckBox#taskCheck[done="true"] {{
    color: {INK_FAINT};
}}
QCheckBox#taskCheck::indicator {{
    width: {CHECKBOX_SIZE}px;
    height: {CHECKBOX_SIZE}px;
    border: 1px solid #D1D5DB;
    border-radius: 4px;
    background: {PAPER_RAISED};
}}
QCheckBox#taskCheck::indicator:hover {{
    border-color: {INK_MARK};
}}
QCheckBox#taskCheck::indicator:checked {{
    background: {INK_MARK};
    border-color: {INK_MARK};
    image: url("{CHECK_URL}");
}}

/* The rename/delete affordance: holds its place in the layout always, and
   only takes on colour while its row is hovered, so nothing shifts. */
QPushButton#rowMenu {{
    background: transparent;
    border: none;
    color: transparent;
    font-size: 15px;
    padding: 0;
}}
QPushButton#rowMenu[revealed="true"] {{
    color: {INK_FAINT};
}}
QPushButton#rowMenu[revealed="true"]:hover {{
    color: {INK};
}}

QLabel#taskMeta {{
    color: {INK_FAINT};
    font-size: {TEXT_META}px;
    background: transparent;
}}
QLabel#taskMeta[overdue="true"] {{
    color: {DANGER};
}}

QLabel#emptyNote {{
    color: {INK_FAINT};
    font-size: {TEXT_META}px;
    background: transparent;
    padding-left: {SPACE_6}px;
}}

QLabel#bigEmpty {{
    color: {INK_SOFT};
    font-size: {TEXT_BODY}px;
    background: transparent;
}}

/* ---- the + button ---- */
QPushButton#addButton {{
    background: transparent;
    color: {INK_SOFT};
    border: none;
    border-radius: 4px;
    font-size: 24px;
    font-weight: 400;
    padding: 0 0 4px 0;
}}
QPushButton#addButton:hover   {{ background: {HOVER}; color: {INK}; }}
QPushButton#addButton:pressed {{ background: {LINE}; }}

QPushButton#archiveButton {{
    background: transparent;
    border: none;
    border-radius: 4px;
}}
QPushButton#archiveButton:hover   {{ background: {HOVER}; }}
QPushButton#archiveButton:pressed,
QPushButton#archiveButton:checked {{ background: {LINE}; }}

/* While the archive is open it reads as a third, selected tab: the real tabs
   step down to unselected so only one label carries the underline. */
QTabBar[archiveOpen="true"]::tab:selected {{
    color: {INK_FAINT};
    border-bottom: 2px solid transparent;
}}
QTabBar[archiveOpen="true"]::tab:selected:hover {{
    color: {INK_SOFT};
}}
QLabel#archiveHeading {{
    color: {INK};
    background: transparent;
    padding: {SPACE_2}px {SPACE_4}px;
    border-bottom: 2px solid {ACCENT};
    font-size: {TEXT_BODY}px;
    font-weight: 500;
}}

/* Rounded like a Mac menu. This only reads as rounded because rounded_menu()
   makes the popup window translucent; see widgets.rounded_menu. */
QMenu {{
    background: {PAPER_RAISED};
    border: 1px solid {LINE};
    border-radius: {MENU_RADIUS}px;
    padding: {SPACE_1}px;
}}
QMenu::item {{
    padding: {SPACE_2}px {SPACE_4}px;
    margin: 0 {SPACE_1}px;
    border-radius: {MENU_ITEM_RADIUS}px;
    color: {INK};
}}
QMenu::item:selected {{
    background: {HOVER};
    color: {INK};
}}

/* ---- status bar ---- */
QStatusBar {{
    background: transparent;
    border-top: 1px solid {LINE};
    color: {INK_FAINT};
    font-size: {TEXT_META}px;
}}
QStatusBar::item {{ border: none; }}
/* QStatusBar lays out its items by hand and ignores its own padding, so the
   gap from the window edge lives on the labels. */
QLabel#statusText {{
    color: {INK_FAINT};
    font-size: {TEXT_META}px;
    background: transparent;
    padding: 0 {SPACE_3}px;
}}

/* ---- dialogs ---- */
QDialog {{ background: {PAPER}; }}

QLabel#fieldLabel {{
    color: {INK_SOFT};
    font-size: {TEXT_META}px;
    font-weight: 500;
    background: transparent;
}}
QLabel#dialogTitle {{
    color: {INK};
    font-size: 18px;
    font-weight: 600;
    background: transparent;
}}
QLabel#hint {{
    color: {INK_FAINT};
    font-size: {TEXT_META}px;
    background: transparent;
}}
QLabel#hint[warn="true"] {{
    color: {DANGER};
}}
QLabel#errorNote {{
    color: {DANGER};
    font-size: {TEXT_META}px;
    background: transparent;
}}

QLineEdit, QTextEdit, QDateEdit, QComboBox {{
    background: {PAPER_RAISED};
    border: 1px solid {LINE};
    border-radius: 4px;
    padding: {SPACE_2}px {SPACE_3}px;
    color: {INK};
    font-size: {TEXT_BODY}px;
    selection-background-color: {ACCENT};
    selection-color: #FFFFFF;
}}
QLineEdit:focus, QTextEdit:focus, QDateEdit:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QLineEdit::placeholder {{ color: {INK_FAINT}; }}
QComboBox QAbstractItemView {{
    background: {PAPER_RAISED};
    border: 1px solid {LINE};
    selection-background-color: {HOVER};
    selection-color: {INK};
    outline: none;
}}

QPushButton#primary {{
    background: {ACCENT};
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: {SPACE_2}px {SPACE_4}px;
    font-weight: 500;
}}
QPushButton#primary:hover    {{ background: #1E5FD9; }}
QPushButton#primary:pressed  {{ background: {ACCENT_PRESSED}; }}
QPushButton#primary:disabled {{ background: #BFD3F5; color: #EEF3FD; }}

QPushButton#ghost {{
    background: transparent;
    color: {INK_SOFT};
    border: 1px solid {LINE};
    border-radius: 4px;
    padding: {SPACE_2}px {SPACE_4}px;
    font-weight: 500;
}}
QPushButton#ghost:hover {{
    background: {HOVER};
    color: {INK};
}}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: transparent;
    width: {SPACE_2}px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #D1D5DB;
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {INK_FAINT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    height: 0;
    background: transparent;
}}
"""
