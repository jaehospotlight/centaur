from __future__ import annotations

from api.agent import _MAX_SLACK_MESSAGE_CHARS, _SLACK_TRUNCATED_SUFFIX, _slack_thread_parts, _truncate_slack_message


def test_slack_thread_parts_accepts_canonical_channel_key() -> None:
    assert _slack_thread_parts("C12345678:1730843413.123456") == ("C12345678", "1730843413.123456")


def test_slack_thread_parts_accepts_slack_prefixed_key() -> None:
    assert _slack_thread_parts("slack:C12345678:1730843413.123456") == (
        "C12345678",
        "1730843413.123456",
    )


def test_slack_thread_parts_rejects_non_slack_like_channel_key() -> None:
    assert _slack_thread_parts("test:e2e-1") is None


def test_slack_thread_parts_rejects_non_thread_ts_shape() -> None:
    assert _slack_thread_parts("C12345678:not-a-slack-thread-ts") is None


def test_truncate_slack_message_keeps_short_content() -> None:
    text = "short message"
    assert _truncate_slack_message(text) == text


def test_truncate_slack_message_applies_consistent_limit_and_suffix() -> None:
    text = "x" * (_MAX_SLACK_MESSAGE_CHARS + 200)
    truncated = _truncate_slack_message(text)
    assert len(truncated) <= _MAX_SLACK_MESSAGE_CHARS
    assert truncated.endswith(_SLACK_TRUNCATED_SUFFIX)
