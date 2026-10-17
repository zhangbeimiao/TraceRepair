from pathlib import Path

from tracerepair.models import Task, TaskStatus
from tracerepair.showcase import load_showcase_trace, render_showcase
from tracerepair.store import TraceStore


def test_showcase_renders_safe_trace_without_raw_artifacts(tmp_path: Path) -> None:
    database = tmp_path / "trace.sqlite3"
    store = TraceStore(database)
    task_id = "model-agent-10-demo"
    store.create_task(Task(task_id, "10", "one bad event aborts a batch", "D:/workspace"))
    store.append_event(
        task_id,
        "run_metadata",
        {"agent_version": "0.4.0-dev1", "model": "qwen3.8-flash"},
    )
    store.transition(task_id, TaskStatus.READY, "created")
    store.transition(task_id, TaskStatus.RUNNING, "started")
    store.append_event(
        task_id,
        "model_plan_recorded",
        {"kind": "tool", "tool": "search_code", "completion_tokens": 30, "policy_accepted": True},
    )
    store.append_event(
        task_id,
        "tool_finished",
        {"tool": "search_code", "ok": True, "summary": {"hit_count": 1}},
    )
    store.transition(task_id, TaskStatus.AWAITING_REVIEW, "all tests passed")
    store.close()

    output = render_showcase(load_showcase_trace(database, task_id))

    assert "model -> search_code" in output
    assert "tool search_code -> ok=True" in output
    assert "Final status: awaiting_review" in output
    assert "D:/workspace" not in output
