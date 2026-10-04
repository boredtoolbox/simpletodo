import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simpletodo.dates import Bucket, bucket_matches, buckets_for  # noqa: E402

TODAY = date(2026, 10, 2)


def at(offset: int) -> date:
    return TODAY + timedelta(days=offset)


def test_today_includes_today_and_overdue():
    assert bucket_matches(at(0), Bucket.TODAY, TODAY)
    assert bucket_matches(at(-1), Bucket.TODAY, TODAY)
    assert bucket_matches(at(-30), Bucket.TODAY, TODAY)
    assert not bucket_matches(at(1), Bucket.TODAY, TODAY)


def test_tomorrow_is_exactly_one_day_out():
    assert bucket_matches(at(1), Bucket.TOMORROW, TODAY)
    assert not bucket_matches(at(0), Bucket.TOMORROW, TODAY)
    assert not bucket_matches(at(2), Bucket.TOMORROW, TODAY)


def test_this_week_spans_today_through_six_days():
    for offset in range(0, 7):
        assert bucket_matches(at(offset), Bucket.THIS_WEEK, TODAY)
    assert not bucket_matches(at(7), Bucket.THIS_WEEK, TODAY)
    assert not bucket_matches(at(-1), Bucket.THIS_WEEK, TODAY)


def test_rest_is_beyond_six_days():
    assert bucket_matches(at(7), Bucket.REST, TODAY)
    assert bucket_matches(at(90), Bucket.REST, TODAY)
    assert not bucket_matches(at(6), Bucket.REST, TODAY)


def test_a_task_may_sit_in_two_sections():
    assert buckets_for(at(0), TODAY) == [Bucket.TODAY, Bucket.THIS_WEEK]
    assert buckets_for(at(1), TODAY) == [Bucket.TOMORROW, Bucket.THIS_WEEK]
    assert buckets_for(at(-5), TODAY) == [Bucket.TODAY]
    assert buckets_for(at(10), TODAY) == [Bucket.REST]


def test_every_date_lands_somewhere():
    for offset in range(-10, 40):
        assert buckets_for(at(offset), TODAY)
