import pytest

from eventrelay import EventProcessor
from eventrelay.validator import parse_event


def test_duplicate_event_is_not_processed_twice(event_payload: dict[str, object]) -> None:
    processed: list[str] = []
    processor = EventProcessor(lambda event: processed.append(event.event_id))

    assert processor.handle(event_payload).status == "processed"
    assert processor.handle(event_payload).status == "duplicate"
    assert processed == ["evt-001"]


def test_failed_handler_does_not_mark_event_processed(event_payload: dict[str, object]) -> None:
    def fail_once(_: object) -> None:
        raise RuntimeError("downstream unavailable")

    processor = EventProcessor(fail_once)
    event = parse_event(event_payload)
    with pytest.raises(RuntimeError, match="downstream unavailable"):
        processor.handle(event_payload)
    assert processor.idempotency.seen(event) is False


def test_bad_item_does_not_abort_batch(event_payload: dict[str, object]) -> None:
    bad = {"event_id": "evt-bad", "payload": "not-a-dict"}
    good = {**event_payload, "event_id": "evt-good"}
    results = EventProcessor().handle_batch([bad, good])
    assert [result.status for result in results] == ["rejected", "processed"]
