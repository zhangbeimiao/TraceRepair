from datetime import UTC, datetime

import pytest


@pytest.fixture
def event_payload() -> dict[str, object]:
    return {
        "event_id": "evt-001",
        "event_type": "payment.completed",
        "occurred_at": datetime(2026, 10, 15, 10, 0, tzinfo=UTC).isoformat(),
        "payload": {"amount": 100},
    }
