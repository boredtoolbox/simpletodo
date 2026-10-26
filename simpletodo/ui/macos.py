"""The one piece of AppKit that Qt does not expose.

The window runs its content up under a transparent title bar
(Qt.ExpandedClientAreaHint), so the traffic lights sit inside the sidebar as
they do in Notes. Qt hides the title bar's background but not its text, which
would be drawn across the top bar's buttons. NSWindow.titleVisibility hides
it; the title itself stays set, so the Dock and the Window menu still name
the window.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import sys

from PySide6.QtWidgets import QWidget

log = logging.getLogger(__name__)

_NS_WINDOW_TITLE_HIDDEN = 1


def hide_title_text(window: QWidget) -> None:
    """Stop macOS drawing *window*'s title. A no-op anywhere else."""
    if sys.platform != "darwin":
        return
    try:
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]

        def send(receiver, selector, *args, argtypes=()):
            call = ctypes.cast(
                objc.objc_msgSend,
                ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                 *argtypes),
            )
            return call(receiver, objc.sel_registerName(selector), *args)

        # On cocoa, winId() is the window's NSView.
        ns_window = send(int(window.winId()), b"window")
        if ns_window:
            send(ns_window, b"setTitleVisibility:", _NS_WINDOW_TITLE_HIDDEN,
                 argtypes=(ctypes.c_long,))
    except (OSError, AttributeError, TypeError) as exc:
        # Cosmetic only: the title shows, and everything still works.
        log.debug("could not hide the window title: %s", exc)
