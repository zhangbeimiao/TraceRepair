from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Event:
    event_id: str
    event_type: str
    occurred_at: datetime
    payload: dict[str, Any]


@dataclass(frozen=True)
class EventResult:
    event_id: str
    status: str
    detail: str = ""
