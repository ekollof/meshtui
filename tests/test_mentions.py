"""Tests for channel @mention completion."""

from meshtui.mentions import (
    complete_mention,
    format_mention,
    message_mentions,
    nicknames_from_messages,
)


def test_format_mention_matches_official_apps():
    assert format_mention("Alice") == "@[Alice]: "


def test_complete_at_prefix():
    assert complete_mention("@Al", ["Alice", "Bob"]) == "@[Alice]: "


def test_complete_bracket_prefix():
    assert complete_mention("@[bo", ["Alice", "Bob"]) == "@[Bob]: "


def test_complete_bare_at_uses_first_name():
    assert complete_mention("@", ["Carol", "Alice"]) == "@[Carol]: "


def test_complete_mid_sentence():
    assert (
        complete_mention("path looks good @[al", ["Alice"])
        == "path looks good @[Alice]: "
    )


def test_no_match_returns_none():
    assert complete_mention("@zz", ["Alice"]) is None
    assert complete_mention("hello there", ["Alice"]) is None


def test_closed_mention_not_completed_again():
    assert complete_mention("@[Alice]: more text", ["Alice", "Bob"]) is None


def test_nicknames_prefer_recent_channel_senders():
    messages = [
        {"sender": "Old"},
        {"sender": "Alice"},
        {"sender": "Bob"},
        {"sender": "Me"},
    ]
    names = nicknames_from_messages(messages, extra=["Carol"], exclude=["Me"])
    assert names[0] == "Bob"
    assert names[1] == "Alice"
    assert "Me" not in names
    assert "Carol" in names


def test_message_mentions_own_name():
    assert message_mentions("@[Radio]: hello", "Radio")
    assert message_mentions("@[radio]: hello", "Radio")
    assert not message_mentions("plain hello", "Radio")
