"""Input rules for project and task fields.

Names accept letters, digits, spaces and "|". Anything else is dropped as it
is typed. Surrounding whitespace is trimmed, so a name of only spaces counts
as empty.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

NAME_MAX_LENGTH = 50
DESCRIPTION_MAX_WORDS = 300

#: A single permitted name character: alphanumeric, space, or the pipe.
NAME_CHAR_RE = re.compile(r"[^0-9A-Za-z| ]")

#: Patterns that betray a hyperlink in a description.
_LINK_PATTERNS = (
    re.compile(r"\b[a-z][a-z0-9+.-]*://", re.IGNORECASE),      # scheme://
    re.compile(r"\bwww\.[a-z0-9-]+\.[a-z]{2,}", re.IGNORECASE),  # www.host.tld
    re.compile(
        r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|net|io|dev|edu|gov|co|uk|de"
        r"|fr|app|ai|sh|me|info|biz|xyz)\b(?:/\S*)?",
        re.IGNORECASE,
    ),  # bare host.tld
    re.compile(r"\bmailto:", re.IGNORECASE),
)


def sanitize_name(text: str) -> str:
    """Strip every character a name may not contain."""
    return NAME_CHAR_RE.sub("", text)


def count_words(text: str) -> int:
    """Number of whitespace-separated words in *text*."""
    return len(text.split())


def find_hyperlink(text: str) -> str | None:
    """Return the first hyperlink-looking substring, or None."""
    for pattern in _LINK_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


@dataclass(frozen=True)
class Result:
    """The outcome of validating one field."""

    ok: bool
    message: str = ""

    def __bool__(self) -> bool:
        return self.ok


VALID = Result(True)


def validate_name(name: str, *, label: str = "Name") -> Result:
    name = name.strip()
    if not name:
        return Result(False, f"{label} is required.")
    if len(name) > NAME_MAX_LENGTH:
        return Result(False, f"{label} may be at most {NAME_MAX_LENGTH} characters.")
    if NAME_CHAR_RE.search(name):
        return Result(
            False, f"{label} may contain letters, digits, spaces and | only."
        )
    return VALID


def validate_description(text: str) -> Result:
    words = count_words(text)
    if words > DESCRIPTION_MAX_WORDS:
        return Result(
            False,
            f"Description is {words} words; the limit is {DESCRIPTION_MAX_WORDS}.",
        )
    link = find_hyperlink(text)
    if link:
        return Result(False, f"Description may not contain links (found “{link}”).")
    return VALID
