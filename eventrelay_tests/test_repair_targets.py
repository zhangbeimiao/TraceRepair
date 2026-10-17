from datetime import UTC

import pytest

from eventrelay import EventProcessor
from eventrelay.config import read_bool
from eventrelay.models import Event
from eventrelay.retry import RetryableError, is_retryable_status, retry
from eventrelay.retention import RetryRecord, expired_event_ids
from eventrelay.storage import EventStore
from eventrelay.validator import parse_event


def test_case_01_uses_event_id_for_idempotency(event_payload: dict[str, object]) -> None:
    processor = EventProcessor()
    assert processor.handle(event_payload).status == "processed"
    other = {**event_payload, "event_id": "evt-002"}
    assert processor.handle(other).status == "processed"


def test_case_02_normalizes_naive_timestamp(event_payload: dict[str, object]) -> None:
    event = parse_event({**event_payload, "occurred_at": "2026-10-15T10:00:00"})
    assert event.occurred_at.tzinfo == UTC


def test_case_03_respects_retry_budget() -> None:
    attempts = 0

    def always_fail() -> None:
        nonlocal attempts
        attempts += 1
        raise RetryableError("temporary")

    with pytest.raises(RetryableError):
        retry(always_fail, max_retries=2)
    assert attempts == 3


def test_case_04_retries_rate_limits() -> None:
    assert is_retryable_status(429)


def test_case_05_parses_false_as_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVENT_RETRY_ENABLED", "false")
    assert read_bool("EVENT_RETRY_ENABLED") is False


def test_case_06_rejects_unknown_input(event_payload: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="unknown fields"):
        parse_event({**event_payload, "ignore_safety": True})


def test_case_07_cursor_does_not_repeat(event_payload: dict[str, object]) -> None:
    first = parse_event(event_payload)
    second = parse_event({**event_payload, "event_id": "evt-002", "occurred_at": "2026-10-15T10:01:00Z"})
    store = EventStore()
    store.add(first)
    store.add(second)
    assert store.list_after(first.occurred_at.isoformat(), 10) == [second]


def test_case_08_failed_event_can_be_redelivered(event_payload: dict[str, object]) -> None:
    attempts = 0

    def flaky(_: Event) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary")

    processor = EventProcessor(flaky)
    with pytest.raises(RuntimeError):
        processor.handle(event_payload)
    assert processor.handle(event_payload).status == "processed"


def test_case_09_compares_retention_in_milliseconds() -> None:
    records = [RetryRecord("old", 1000), RetryRecord("new", 9000)]
    assert expired_event_ids(records, now_ms=10_000, retention_ms=5_000) == ["old"]


def test_case_10_isolates_batch_validation(event_payload: dict[str, object]) -> None:
    bad = {"event_id": "bad", "payload": "bad"}
    good = {**event_payload, "event_id": "evt-good"}
    result = EventProcessor().handle_batch([bad, good])
    assert [item.status for item in result] == ["rejected", "processed"]
