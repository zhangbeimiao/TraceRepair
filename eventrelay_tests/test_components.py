from datetime import UTC, datetime, timedelta

import pytest

from eventrelay.config import read_bool
from eventrelay.models import Event
from eventrelay.retry import RetryableError, is_retryable_status, retry
from eventrelay.retention import RetryRecord, expired_event_ids
from eventrelay.storage import EventStore
from eventrelay.validator import parse_event


def test_boolean_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVENT_RETRY_ENABLED", "false")
    assert read_bool("EVENT_RETRY_ENABLED") is False


def test_unknown_field_is_rejected(event_payload: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="unknown fields"):
        parse_event({**event_payload, "ignore_safety": True})


def test_timezone_is_normalized(event_payload: dict[str, object]) -> None:
    parsed = parse_event({**event_payload, "occurred_at": "2026-10-15T18:00:00+08:00"})
    assert parsed.occurred_at == datetime(2026, 10, 15, 10, 0, tzinfo=UTC)


def test_retry_count_means_retries_after_initial_attempt() -> None:
    attempts = 0

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RetryableError("temporary")
        return "ok"

    assert retry(operation, max_retries=2) == "ok"
    assert attempts == 3


def test_429_is_retryable() -> None:
    assert is_retryable_status(429) is True


def test_cursor_is_exclusive() -> None:
    store = EventStore()
    start = datetime(2026, 10, 15, tzinfo=UTC)
    for index in range(3):
        store.add(Event(f"evt-{index}", "demo", start + timedelta(minutes=index), {}))
    first_page = store.list_after(None, limit=2)
    second_page = store.list_after(first_page[-1].occurred_at.isoformat(), limit=2)
    assert [event.event_id for event in second_page] == ["evt-2"]


def test_expired_retry_records_use_milliseconds() -> None:
    records = [RetryRecord("expired", 1_000), RetryRecord("fresh", 9_500)]
    assert expired_event_ids(records, now_ms=10_000, retention_ms=5_000) == ["expired"]
