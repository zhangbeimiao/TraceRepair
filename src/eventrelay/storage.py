from datetime import UTC, datetime

from eventrelay.models import Event


class EventStore:
    def __init__(self) -> None:
        self._events: list[Event] = []

    def add(self, event: Event) -> None:
        self._events.append(event)

    def list_after(self, cursor: str | None, limit: int) -> list[Event]:
        ordered = sorted(self._events, key=lambda item: (item.occurred_at, item.event_id))
        if cursor is None:
            return ordered[:limit]
        cursor_time = datetime.fromisoformat(cursor.replace("Z", "+00:00")).astimezone(UTC)
        return [item for item in ordered if item.occurred_at > cursor_time][:limit]
