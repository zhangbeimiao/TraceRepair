from pathlib import Path

from evaluation.materialize import materialize_case
from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.langgraph_workflow import LangGraphDiagnosticWorkflow
from tracerepair.models import Task, TaskStatus
from tracerepair.read_tools import ReadOnlyRepository
from tracerepair.store import TraceStore
from tracerepair.test_runner import RestrictedTestRunner


def make_graph(tmp_path: Path, task_id: str = "graph-01") -> tuple[TraceStore, LangGraphDiagnosticWorkflow]:
    workspace = materialize_case("01", tmp_path / "case-01")
    store = TraceStore(tmp_path / "data/trace.sqlite3")
    store.create_task(Task(task_id, "01", "idempotency key is wrong", str(workspace)))
    store.transition(task_id, TaskStatus.READY, "ready for graph")

    def tools_factory() -> InstrumentedTools:
        return InstrumentedTools(
            task_id,
            store,
            ReadOnlyRepository(workspace),
            RestrictedTestRunner(workspace),
        )

    return store, LangGraphDiagnosticWorkflow(task_id, store, tools_factory)


def test_graph_executes_diagnostic_path_and_hands_off(tmp_path: Path) -> None:
    store, graph = make_graph(tmp_path)

    state = graph.invoke()

    assert state["actions"] == ["repo_map", "search_code", "read_file", "run_tests"]
    assert state["task_status"] == TaskStatus.NEEDS_HUMAN
    assert store.get_task("graph-01").status is TaskStatus.NEEDS_HUMAN
    assert [event.event_type for event in store.list_events("graph-01")].count("graph_node_completed") == 4
    store.close()


def test_graph_rebuilds_and_resumes_from_trace_checkpoint(tmp_path: Path) -> None:
    store, graph = make_graph(tmp_path)
    task_id = "graph-01"
    task = store.get_task(task_id)
    store.transition(task_id, TaskStatus.RUNNING, "simulate worker start")
    tools = InstrumentedTools(
        task_id,
        store,
        ReadOnlyRepository(Path(task.workspace)),
        RestrictedTestRunner(Path(task.workspace)),
    )
    assert tools.repo_map().ok is True

    state = graph.invoke()

    assert state["actions"] == ["search_code", "read_file", "run_tests"]
    assert store.get_task(task_id).status is TaskStatus.NEEDS_HUMAN
    store.close()


def test_graph_rejects_unbounded_recursion_limit(tmp_path: Path) -> None:
    store, graph = make_graph(tmp_path)

    try:
        graph.invoke(recursion_limit=31)
    except ValueError as error:
        assert "recursion_limit" in str(error)
    else:
        raise AssertionError("expected a bounded recursion limit")
    store.close()
