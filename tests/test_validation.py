import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simpletodo.validation import (  # noqa: E402
    count_words,
    find_hyperlink,
    sanitize_name,
    validate_description,
    validate_name,
)


def test_sanitize_keeps_alphanumerics_spaces_and_pipe():
    assert sanitize_name("Buy|Milk") == "Buy|Milk"
    assert sanitize_name("Buy Milk!") == "Buy Milk"
    assert sanitize_name("a-b_c.d") == "abcd"
    assert sanitize_name("Taésk 99") == "Task 99"      # non-ASCII dropped
    assert sanitize_name("") == ""


def test_validate_name_rules():
    assert validate_name("Home|Chores")
    assert validate_name("Wash the dishes")
    assert validate_name("Buy milk 2")
    assert not validate_name("")
    assert not validate_name("   ")              # only spaces reads as empty
    assert not validate_name("no\ttabs")
    assert not validate_name("no_underscores")
    assert not validate_name("x" * 51)
    assert validate_name("x" * 50)


def test_name_error_messages_name_the_field():
    assert "Project name" in validate_name("", label="Project name").message


def test_count_words():
    assert count_words("") == 0
    assert count_words("one") == 1
    assert count_words("  two   words \n") == 2


def test_find_hyperlink_catches_common_shapes():
    assert find_hyperlink("see https://example.com/x")
    assert find_hyperlink("go to www.example.org")
    assert find_hyperlink("ping example.com")
    assert find_hyperlink("mail mailto:a@b.c")
    assert find_hyperlink("ftp://host/file")
    assert find_hyperlink("no links at all here") is None
    assert find_hyperlink("version 1.2 of the plan") is None


def test_validate_description_limits():
    assert validate_description("")
    assert validate_description(" ".join(["w"] * 300))
    too_long = validate_description(" ".join(["w"] * 301))
    assert not too_long and "301" in too_long.message
    linked = validate_description("read https://example.com")
    assert not linked and "links" in linked.message
