from datetime import UTC, datetime
from typing import Any

from eventrelay.models import Event

_REQUIRED = {"event_id", "event_type", "occurred_at", "payload"}


def parse_event(raw: dict[str, Any]) -> Event:
    unknown = set(raw) - _REQUIRED
    missing = _REQUIRED - set(raw)
    if unknown:
        raise ValueError(f"unknown fields: {sorted(unknown)}")
    if missing:
        raise ValueError(f"missing fields: {sorted(missing)}")
    if not isinstance(raw["payload"], dict):
        raise ValueError("payload must be an object")

    occurred_at = datetime.fromisoformat(raw["occurred_at"].replace("Z", "+00:00"))
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    else:
        occurred_at = occurred_at.astimezone(UTC)
    return Event(raw["event_id"], raw["event_type"], occurred_at, raw["payload"])
