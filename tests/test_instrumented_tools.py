from pathlib import Path

from evaluation.materialize import materialize_baseline, materialize_case
from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.models import Task, TaskStatus
from tracerepair.patch_apply import PatchApplier
from tracerepair.read_tools import ReadOnlyRepository
from tracerepair.store import TraceStore
from tracerepair.test_runner import RestrictedTestRunner


def running_tools(tmp_path: Path) -> tuple[TraceStore, InstrumentedTools]:
    workspace = materialize_baseline(tmp_path / "eventrelay-workspace")
    store = TraceStore(tmp_path / "data/trace.sqlite3")
    store.create_task(Task("task-tools", "01", "inspect EventRelay", str(workspace)))
    store.transition("task-tools", TaskStatus.READY, "workspace prepared")
    store.transition("task-tools", TaskStatus.RUNNING, "workflow started")
    tools = InstrumentedTools(
        "task-tools",
        store,
        ReadOnlyRepository(workspace),
        RestrictedTestRunner(workspace),
    )
    return store, tools


def test_read_file_creates_trace_and_recoverable_checkpoint(tmp_path: Path) -> None:
    store, tools = running_tools(tmp_path)
    result = tools.read_file("src/eventrelay/config.py", 1, 3)

    assert result.ok is True
    events = store.list_events("task-tools")
    assert [event.event_type for event in events][-3:] == [
        "tool_started",
        "tool_finished",
        "checkpoint_saved",
    ]
    checkpoint = store.load_checkpoint("task-tools")
    assert checkpoint["last_tool"]["tool"] == "read_file"
    assert checkpoint["last_tool"]["summary"]["content_sha256"]
    assert "import os" not in str(checkpoint)
    store.close()


def test_denied_path_is_traceable_without_leaking_content(tmp_path: Path) -> None:
    store, tools = running_tools(tmp_path)
    result = tools.read_file("tests/test_processor.py")

    assert result.ok is False
    checkpoint = store.load_checkpoint("task-tools")
    assert checkpoint["last_tool"]["ok"] is False
    assert checkpoint["last_tool"]["error_code"] == "PATH_DENIED"
    store.close()


def test_test_run_trace_records_metadata_not_raw_output(tmp_path: Path) -> None:
    store, tools = running_tools(tmp_path)
    result = tools.run_tests("tests/test_repair_targets.py::test_case_04_retries_rate_limits")

    assert result.ok is True
    checkpoint = store.load_checkpoint("task-tools")
    summary = checkpoint["last_tool"]["summary"]
    assert summary["exit_code"] == 0
    assert len(summary["stdout_sha256"]) == 64
    assert "passed" not in str(summary)
    store.close()


def test_patch_trace_records_hashes_not_raw_diff(tmp_path: Path) -> None:
    workspace = materialize_case("05", tmp_path / "case-05")
    store = TraceStore(tmp_path / "data/trace.sqlite3")
    store.create_task(Task("task-patch", "05", "retry flag is wrong", str(workspace)))
    store.transition("task-patch", TaskStatus.READY, "workspace prepared")
    store.transition("task-patch", TaskStatus.RUNNING, "workflow started")
    tools = InstrumentedTools(
        "task-patch",
        store,
        ReadOnlyRepository(workspace),
        RestrictedTestRunner(workspace),
        PatchApplier(workspace),
    )
    diff = """--- a/src/eventrelay/config.py
+++ b/src/eventrelay/config.py
@@ -6,6 +6,4 @@
     if value is None:
         return default
     normalized = value.strip().lower()
-    if value:
-        return True
     if normalized in {\"1\", \"true\", \"yes\", \"on\"}:
         return True
"""

    result = tools.apply_patch(diff)

    assert result.ok is True
    checkpoint = store.load_checkpoint("task-patch")
    assert checkpoint["last_tool"]["tool"] == "apply_patch"
    assert checkpoint["last_tool"]["summary"]["files"] == ["src/eventrelay/config.py"]
    assert checkpoint["last_tool"]["summary"]["relocations"] == [
        {
            "path": "src/eventrelay/config.py",
            "advertised_line": 6,
            "applied_line": 6,
            "mode": "advertised",
            "symbol": None,
        }
    ]
    assert "normalized = value" not in str(checkpoint)
    store.close()
