from eventrelay.models import Event


class IdempotencyStore:
    def __init__(self) -> None:
        self._processed: set[str] = set()

    def seen(self, event: Event) -> bool:
        return event.event_id in self._processed

    def mark_processed(self, event: Event) -> None:
        self._processed.add(event.event_id)
