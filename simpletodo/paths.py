"""Platform-appropriate locations for the application's data.

macOS   -> ~/Library/Application Support/simpletodo/
Linux   -> $XDG_DATA_HOME/simpletodo/ (defaults to ~/.local/share/simpletodo/)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "simpletodo"
DB_FILE_NAME = "todo.sqlite3"


def data_dir() -> Path:
    """Return the directory that holds this user's to-do data."""
    override = os.environ.get("SIMPLETODO_DATA_DIR")
    if override:
        return Path(override).expanduser()

    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_DIR_NAME

    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg).expanduser() if xdg else home / ".local" / "share"
    return base / APP_DIR_NAME


def database_path() -> Path:
    return data_dir() / DB_FILE_NAME


def ensure_data_dir() -> Path:
    """Create the data directory if needed and confirm we may write to it.

    Raises OSError with a readable message when the filesystem says no.
    """
    directory = data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    if not os.access(directory, os.W_OK | os.X_OK):
        raise PermissionError(f"No write permission for {directory}")
    return directory
