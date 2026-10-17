from pathlib import Path

import pytest

from tracerepair.models import Task, TaskStatus
from tracerepair.store import TraceStore


def new_task() -> Task:
    return Task("task-001", "01", "Events are incorrectly deduplicated", "D:/case-01")


def test_checkpoint_survives_store_reopen(tmp_path: Path) -> None:
    database = tmp_path / "trace.sqlite3"
    store = TraceStore(database)
    store.create_task(new_task())
    store.transition("task-001", TaskStatus.READY, "workspace verified")
    store.save_checkpoint("task-001", {"attempt": 1, "hypotheses": ["idempotency key"]})
    store.close()

    reopened = TraceStore(database)
    assert reopened.get_task("task-001").status is TaskStatus.READY
    assert reopened.load_checkpoint("task-001") == {
        "attempt": 1,
        "hypotheses": ["idempotency key"],
    }
    assert [event.event_type for event in reopened.list_events("task-001")] == [
        "task_created",
        "status_changed",
        "checkpoint_saved",
    ]
    reopened.close()


def test_invalid_transition_is_rejected(tmp_path: Path) -> None:
    store = TraceStore(tmp_path / "trace.sqlite3")
    store.create_task(new_task())
    with pytest.raises(ValueError, match="invalid transition"):
        store.transition("task-001", TaskStatus.SUCCEEDED, "cannot skip review")
    store.close()


def test_terminal_state_cannot_transition_again(tmp_path: Path) -> None:
    store = TraceStore(tmp_path / "trace.sqlite3")
    store.create_task(new_task())
    store.transition("task-001", TaskStatus.READY, "ready")
    store.transition("task-001", TaskStatus.RUNNING, "started")
    store.transition("task-001", TaskStatus.FAILED_SAFE, "budget exhausted")
    with pytest.raises(ValueError, match="invalid transition"):
        store.transition("task-001", TaskStatus.READY, "retry")
    store.close()
