from dataclasses import dataclass


@dataclass(frozen=True)
class RetryRecord:
    event_id: str
    recorded_at_ms: int


def expired_event_ids(
    records: list[RetryRecord], now_ms: int, retention_ms: int
) -> list[str]:
    cutoff_ms = now_ms - retention_ms
    return [record.event_id for record in records if record.recorded_at_ms < cutoff_ms]
