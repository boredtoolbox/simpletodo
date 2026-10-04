"""The four date buckets of the Date tab.

A task may land in more than one bucket -- an item due today is in both Today
and This Week -- which the specification calls for explicitly.
"""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum

#: How many days beyond today "This Week" reaches.
WEEK_SPAN_DAYS = 6


class Bucket(Enum):
    TODAY = "Today"
    TOMORROW = "Tomorrow"
    THIS_WEEK = "This Week"
    REST = "Rest"

    @property
    def label(self) -> str:
        return self.value


def bucket_matches(due: date, bucket: Bucket, today: date | None = None) -> bool:
    """Does a task due on *due* belong in *bucket*?"""
    today = today or date.today()
    tomorrow = today + timedelta(days=1)
    week_end = today + timedelta(days=WEEK_SPAN_DAYS)

    if bucket is Bucket.TODAY:
        # Overdue work is surfaced alongside today's.
        return due <= today
    if bucket is Bucket.TOMORROW:
        return due == tomorrow
    if bucket is Bucket.THIS_WEEK:
        return today <= due <= week_end
    return due > week_end


def buckets_for(due: date, today: date | None = None) -> list[Bucket]:
    """Every bucket a task due on *due* appears in."""
    return [b for b in Bucket if bucket_matches(due, b, today)]
