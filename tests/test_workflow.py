from pathlib import Path

from evaluation.materialize import materialize_case
from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.models import Task, TaskStatus
from tracerepair.read_tools import ReadOnlyRepository
from tracerepair.store import TraceStore
from tracerepair.test_runner import RestrictedTestRunner
from tracerepair.workflow import DeterministicWorkflow


def create_workflow(tmp_path: Path) -> tuple[TraceStore, DeterministicWorkflow]:
    workspace = materialize_case("01", tmp_path / "case-01")
    store = TraceStore(tmp_path / "data/trace.sqlite3")
    store.create_task(Task("workflow-01", "01", "Distinct events are discarded", str(workspace)))
    store.transition("workflow-01", TaskStatus.READY, "workspace materialised")
    store.transition("workflow-01", TaskStatus.RUNNING, "tool adapter attached")
    tools = InstrumentedTools(
        "workflow-01",
        store,
        ReadOnlyRepository(workspace),
        RestrictedTestRunner(workspace),
    )
    return store, DeterministicWorkflow("workflow-01", store, tools)


def test_workflow_runs_fixed_diagnostics_then_stops_for_human(tmp_path: Path) -> None:
    store, workflow = create_workflow(tmp_path)

    steps = workflow.run_to_stop()

    assert [step.action for step in steps] == ["repo_map", "search_code", "read_file", "run_tests"]
    assert steps[-1].task_status is TaskStatus.NEEDS_HUMAN
    checkpoint = store.load_checkpoint("workflow-01")
    assert [item["tool"] for item in checkpoint["completed_tools"]] == [
        "repo_map",
        "search_code",
        "read_file",
        "run_tests",
    ]
    assert checkpoint["last_tool"]["ok"] is False
    store.close()


def test_workflow_resumes_from_checkpoint_without_repeating_map(tmp_path: Path) -> None:
    store, workflow = create_workflow(tmp_path)
    first = workflow.step()
    second = workflow.step()

    assert first.action == "repo_map"
    assert second.action == "search_code"
    events = store.list_events("workflow-01")
    assert [event.payload["tool"] for event in events if event.event_type == "tool_started"] == [
        "repo_map",
        "search_code",
    ]
    store.close()


def test_workflow_refuses_to_restart_terminal_task(tmp_path: Path) -> None:
    store, workflow = create_workflow(tmp_path)
    store.transition("workflow-01", TaskStatus.NEEDS_HUMAN, "operator stopped task")

    step = workflow.step()

    assert step.action == "stop"
    assert step.task_status is TaskStatus.NEEDS_HUMAN
    store.close()
