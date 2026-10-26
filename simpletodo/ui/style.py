"""One stylesheet for the whole application.

Modelled on the Apple Notes window: a white ground, a sidebar list whose
selection is a soft grey rounded slab, hairline dividers, a top bar of round
buttons and a search pill, round checkboxes. The greys were sampled from Notes
screenshots; the accent is the blue of the app icon, not Notes' yellow.
"""

from __future__ import annotations

from pathlib import Path

#: Qt stylesheets need a real path for url(); resolve it next to this module.
_ASSETS = Path(__file__).resolve().parent / "assets"
CHECK_URL = _ASSETS.joinpath("check.svg").as_posix()
CHEVRON_URL = _ASSETS.joinpath("chevron.svg").as_posix()
FONTS_DIR = _ASSETS / "fonts"

# -- colour -------------------------------------------------------------

SURFACE = "#FFFFFF"        # the window, both panes, inputs and menus
SELECTED = "#D7D7D7"       # the selected sidebar item
HOVER = "#F2F2F2"          # the only hover treatment
SEGMENT_TRACK = "#EFEFEF"  # the groove behind the Projects/Date/Archive switch

INK = "#272727"            # primary text, never pure black
INK_SOFT = "#808080"       # secondary text
INK_FAINT = "#B0B0B0"      # tertiary text, completed tasks, placeholders

LINE = "#E6E6E6"           # borders and dividers
RING = "#BCBCBC"           # an unticked checkbox
ACCENT = "#1468C8"         # the app icon's blue: ticks, focus, the primary button
ACCENT_HOVER = "#115BB0"
ACCENT_PRESSED = "#0E4F99"
ACCENT_RING = "#89B3E3"    # focus ring: the accent at half strength, as Notes does
ACCENT_WASH = "#C4D9F1"    # selected text in a field
BUTTON_GREY = "#ECECEC"    # a dialog's secondary button
BUTTON_GREY_HOVER = "#E2E2E2"
DANGER = "#DC2626"         # overdue only

# -- spacing ------------------------------------------------------------

#: The 4px grid every margin and padding in the app snaps to.
SPACE_1, SPACE_2, SPACE_3, SPACE_4, SPACE_6, SPACE_8 = 4, 8, 12, 16, 24, 32

#: The sidebar's fixed width. Wide enough for a 50-character project name to
#: show its first few words before eliding.
SIDEBAR_WIDTH = 264

#: Inset of sidebar items from the sidebar's edges, and of their text from
#: the item's edges. The selection slab spans the first; text and dividers
#: start after both.
SIDEBAR_GUTTER = SPACE_2
ITEM_PADDING = SPACE_4

# -- type ---------------------------------------------------------------

#: The one face the application is set in. Inter ships in assets/fonts so it
#: looks the same on macOS and Ubuntu; the system UI face is the fallback.
FONT_FAMILY = "Inter"
FONT_FILES = ("Inter-Regular.ttf", "Inter-Medium.ttf",
              "Inter-SemiBold.ttf", "Inter-Bold.ttf")

#: Corner radii in the macOS idiom.
MENU_RADIUS = 10
MENU_ITEM_RADIUS = 5
ITEM_RADIUS = 8            # sidebar selection, task hover

#: Height of the round top-bar buttons and the search pill.
TOOL_SIZE = 28
SEARCH_WIDTH = 200

#: Side of the round checkbox. Shared so the description below a task can
#: line up with the task name rather than with the checkbox.
CHECKBOX_SIZE = 20

TEXT_TITLE = 24              # the pane heading
TEXT_MASTHEAD = 18           # "Simple To Do", atop the sidebar
TEXT_TASK = 15               # task names
TEXT_BODY = 13               # sidebar items, inputs, buttons
TEXT_META = 12               # counts, dates, hints


#: Top-bar glyphs, drawn as line art in the ink they are given. Kept here, not
#: in assets/, because their colour comes from the tokens above.
_ICONS = {
    # a square with a pencil across its corner: write a new task
    "compose": """
      <path d="M9 3.5 H5 A1.5 1.5 0 0 0 3.5 5 V15 A1.5 1.5 0 0 0 5 16.5 H15
               A1.5 1.5 0 0 0 16.5 15 V11"/>
      <path d="M14.6 2.9 L17.1 5.4 L10.2 12.3 L7.2 12.8 L7.7 9.8 Z"/>""",
    "more": """
      <circle cx="4.5" cy="10" r="1.1" fill="{ink}" stroke="none"/>
      <circle cx="10" cy="10" r="1.1" fill="{ink}" stroke="none"/>
      <circle cx="15.5" cy="10" r="1.1" fill="{ink}" stroke="none"/>""",
    "search": """
      <circle cx="8.5" cy="8.5" r="5"/>
      <path d="M12.3 12.3 L16.5 16.5"/>""",
}

_ICON_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20">
  <g fill="none" stroke="{ink}" stroke-width="1.5"
     stroke-linecap="round" stroke-linejoin="round">{body}
  </g>
</svg>
"""


def icon_svg(name: str, ink: str = INK_SOFT) -> bytes:
    body = _ICONS[name].replace("{ink}", ink)
    return _ICON_SVG.replace("{body}", body).replace("{ink}", ink).encode()


def load_fonts() -> str:
    """Register the bundled faces and return the family to set text in.

    Requires a QApplication. Registering is idempotent, so calling this more
    than once costs only a few file reads.
    """
    from PySide6.QtGui import QFontDatabase

    families: set[str] = set()
    for name in FONT_FILES:
        font_id = QFontDatabase.addApplicationFont(str(FONTS_DIR / name))
        if font_id >= 0:
            families.update(QFontDatabase.applicationFontFamilies(font_id))
    if FONT_FAMILY in families:
        return FONT_FAMILY
    # Never name a family that is not installed: Qt would scan its alias
    # table for it, costing ~140ms at startup.
    return QFontDatabase.systemFont(QFontDatabase.GeneralFont).family()


def stylesheet(font_family: str | None = None) -> str:
    """The application stylesheet, bound to a font family that exists."""
    family = font_family or load_fonts()
    return _TEMPLATE.replace("__FONT_FAMILY__", family)


_TEMPLATE = f"""
QWidget {{
    background: {SURFACE};
    color: {INK};
    font-family: "__FONT_FAMILY__";
    font-size: {TEXT_BODY}px;
    font-weight: 400;
}}

QScrollArea, QScrollArea > QWidget > QWidget,
QWidget#sidebarList, QWidget#paneColumn, QWidget#sidebarHeader {{
    background: transparent;
}}
QWidget#sidebarColumn {{
    background: {SURFACE};
    border-right: 1px solid {LINE};
}}

/* ---- the top bar ---- */
QWidget#topBar {{ background: transparent; }}
QPushButton#toolButton {{
    background: {SURFACE};
    border: 1px solid {LINE};
    border-radius: {TOOL_SIZE // 2}px;
    padding: 0;
}}
QPushButton#toolButton:hover   {{ background: {HOVER}; }}
QPushButton#toolButton:pressed {{ background: {LINE}; }}
QPushButton#toolButton:disabled {{ background: {SURFACE}; border-color: {HOVER}; }}
QLineEdit#searchField {{
    background: {SURFACE};
    border: 1px solid {LINE};
    border-radius: {TOOL_SIZE // 2}px;
    padding: 0 {SPACE_3}px 0 {SPACE_1}px;
    min-height: {TOOL_SIZE - 2}px;
    max-height: {TOOL_SIZE - 2}px;
}}
QLineEdit#searchField:focus {{ border-color: {ACCENT_RING}; }}

/* ---- sidebar header ---- */
QLabel#appTitle {{
    font-size: {TEXT_MASTHEAD}px;
    font-weight: 700;
    color: {INK};
    background: transparent;
}}

QPushButton#addButton {{
    background: transparent;
    color: {INK_SOFT};
    border: none;
    border-radius: 6px;
    font-size: 22px;
    font-weight: 400;
    padding: 0 0 3px 0;
}}
QPushButton#addButton:hover   {{ background: {HOVER}; color: {INK}; }}
QPushButton#addButton:pressed {{ background: {LINE}; }}

/* The Projects / Date / Archive switch: a grey groove holding a white
   segment for the one that is on. */
QWidget#segmentBar {{
    background: {SEGMENT_TRACK};
    border-radius: 8px;
}}
QPushButton#segment {{
    background: transparent;
    color: {INK_SOFT};
    border: 1px solid transparent;
    border-radius: 6px;
    padding: {SPACE_1}px {SPACE_2}px;
    font-size: {TEXT_META}px;
    font-weight: 500;
}}
QPushButton#segment:hover {{ color: {INK}; }}
QPushButton#segment:checked {{
    background: {SURFACE};
    border-color: {LINE};
    color: {INK};
    font-weight: 600;
}}

/* ---- sidebar items ---- */
QFrame#sidebarItem {{
    background: transparent;
    border-radius: {ITEM_RADIUS}px;
}}
QFrame#sidebarItem:hover {{
    background: {HOVER};
}}
QFrame#sidebarItem[selected="true"] {{
    background: {SELECTED};
}}
QLabel#itemTitle {{
    color: {INK};
    font-size: {TEXT_BODY}px;
    font-weight: 700;
    background: transparent;
}}
QLabel#itemStrong {{
    color: {INK};
    font-size: {TEXT_BODY}px;
    background: transparent;
}}
QLabel#itemSoft {{
    color: {INK_SOFT};
    font-size: {TEXT_BODY}px;
    background: transparent;
}}
/* Always 1px tall so nothing moves; clear beside the selection, as in Notes. */
QFrame#sidebarDivider {{
    background: {LINE};
    border: none;
    margin: 0 {ITEM_PADDING}px;
}}
QFrame#sidebarDivider[clear="true"] {{
    background: transparent;
}}

QLabel#emptyNote {{
    color: {INK_FAINT};
    font-size: {TEXT_BODY}px;
    background: transparent;
    padding-left: {SPACE_2}px;
}}

/* ---- the task pane ---- */
QLabel#paneTitle {{
    color: {INK};
    font-size: {TEXT_TITLE}px;
    font-weight: 700;
    background: transparent;
}}
QLabel#paneSubtitle {{
    color: {INK_SOFT};
    font-size: {TEXT_META}px;
    background: transparent;
}}

QWidget#taskRow, QWidget#taskDescriptionPanel {{
    background: transparent;
}}
QWidget#taskLine {{
    background: transparent;
    border-radius: 6px;
}}
QWidget#taskLine:hover {{
    background: {HOVER};
}}

QLabel#taskName {{
    color: {INK};
    font-size: {TEXT_TASK}px;
    background: transparent;
}}
QLabel#taskName[done="true"] {{
    color: {INK_FAINT};
    text-decoration: line-through;
}}
/* Only a task that has something to show invites a click. */
QLabel#taskName[expandable="true"]:hover {{
    color: {INK_SOFT};
}}
QLabel#taskDescription {{
    color: {INK_SOFT};
    font-size: {TEXT_BODY}px;
    background: transparent;
}}

QCheckBox#taskCheck {{
    /* No label of its own, so no gap to reserve for one. */
    spacing: 0;
    padding: {SPACE_1}px 0;
    background: transparent;
}}
QCheckBox#taskCheck::indicator {{
    width: {CHECKBOX_SIZE - 2}px;
    height: {CHECKBOX_SIZE - 2}px;
    border: 1px solid {RING};
    border-radius: {CHECKBOX_SIZE // 2}px;
    background: {SURFACE};
}}
QCheckBox#taskCheck::indicator:hover {{
    border-color: {INK_SOFT};
}}
QCheckBox#taskCheck::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
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
    color: {INK_SOFT};
}}
QPushButton#rowMenu[revealed="true"]:hover {{
    color: {INK};
}}

QLabel#taskMeta {{
    color: {INK_SOFT};
    font-size: {TEXT_META}px;
    background: transparent;
}}
QLabel#taskMeta[overdue="true"] {{
    color: {DANGER};
}}

QLabel#bigEmpty {{
    color: {INK_SOFT};
    font-size: {TEXT_BODY}px;
    background: transparent;
}}

/* Rounded like a Mac menu. This only reads as rounded because rounded_menu()
   makes the popup window translucent; see widgets.rounded_menu. */
QMenu {{
    background: {SURFACE};
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
    background: {SURFACE};
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

/* ---- dialogs: laid out like a Notes sheet ---- */
QDialog {{ background: {SURFACE}; }}

QLabel#dialogTitle {{
    color: {INK};
    font-size: 15px;
    font-weight: 700;
    background: transparent;
}}
QLabel#fieldLabel {{
    color: {INK};
    font-size: {TEXT_BODY}px;
    background: transparent;
}}
QLabel#dialogMessage {{
    color: {INK};
    font-size: {TEXT_BODY}px;
    background: transparent;
}}
QLabel#hint {{
    color: {INK_SOFT};
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
QFrame#dialogDivider {{
    background: {LINE};
    border: none;
}}

/* A focused field wears a thick, soft accent ring. The 2px the ring adds
   comes out of the padding, so the text does not move when focus arrives. */
QLineEdit, QTextEdit, QDateEdit, QComboBox {{
    background: {SURFACE};
    border: 1px solid {LINE};
    border-radius: 7px;
    padding: {SPACE_1 + 2}px {SPACE_2 + 2}px;
    color: {INK};
    font-size: {TEXT_BODY}px;
    selection-background-color: {ACCENT_WASH};
    selection-color: {INK};
}}
QLineEdit:focus, QTextEdit:focus, QDateEdit:focus, QComboBox:focus {{
    border: 3px solid {ACCENT_RING};
    padding: {SPACE_1}px {SPACE_2}px;
}}
QLineEdit::placeholder {{ color: {INK_FAINT}; }}
/* Fusion boxes the drop-down arrow in a hard-edged button; a bare chevron
   is all a Mac pop-up shows. */
QComboBox::drop-down, QDateEdit::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    border: none;
    width: {SPACE_6}px;
}}
QComboBox::down-arrow, QDateEdit::down-arrow {{
    image: url("{CHEVRON_URL}");
    width: 10px;
    height: 10px;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 1px solid {LINE};
    selection-background-color: {HOVER};
    selection-color: {INK};
    outline: none;
}}

QPushButton#primary {{
    background: {ACCENT};
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: {SPACE_1 + 1}px {SPACE_4}px;
    min-width: 64px;
    font-weight: 500;
}}
QPushButton#primary:hover    {{ background: {ACCENT_HOVER}; }}
QPushButton#primary:pressed  {{ background: {ACCENT_PRESSED}; }}
QPushButton#primary:disabled {{ background: {ACCENT_WASH}; color: #FFFFFF; }}

QPushButton#ghost {{
    background: {BUTTON_GREY};
    color: {INK};
    border: none;
    border-radius: 6px;
    padding: {SPACE_1 + 1}px {SPACE_4}px;
    min-width: 64px;
    font-weight: 500;
}}
QPushButton#ghost:hover   {{ background: {BUTTON_GREY_HOVER}; }}
QPushButton#ghost:pressed {{ background: {LINE}; }}

QScrollArea {{ border: none; }}
QScrollBar:vertical {{
    background: transparent;
    width: {SPACE_2}px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {LINE};
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
