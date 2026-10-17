from collections.abc import Callable
from typing import Any

from eventrelay.idempotency import IdempotencyStore
from eventrelay.models import Event, EventResult
from eventrelay.storage import EventStore
from eventrelay.validator import parse_event


class EventProcessor:
    def __init__(self, handler: Callable[[Event], None] | None = None) -> None:
        self._handler = handler or (lambda _: None)
        self.idempotency = IdempotencyStore()
        self.store = EventStore()

    def handle(self, raw: dict[str, Any]) -> EventResult:
        event = parse_event(raw)
        if self.idempotency.seen(event):
            return EventResult(event.event_id, "duplicate")
        self._handler(event)
        self.idempotency.mark_processed(event)
        self.store.add(event)
        return EventResult(event.event_id, "processed")

    def handle_batch(self, items: list[dict[str, Any]]) -> list[EventResult]:
        results: list[EventResult] = []
        for item in items:
            try:
                results.append(self.handle(item))
            except ValueError as error:
                event_id = str(item.get("event_id", "unknown"))
                results.append(EventResult(event_id, "rejected", str(error)))
        return results
