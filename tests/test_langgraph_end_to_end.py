import json
from pathlib import Path

import pytest

from evaluation.materialize import materialize_case
from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.langgraph_end_to_end import LangGraphEndToEndRepairWorkflow
from tracerepair.model_planner import ModelPlanner, PlannerConfig
from tracerepair.models import Task, TaskStatus
from tracerepair.patch_apply import PatchApplier
from tracerepair.read_tools import ReadOnlyRepository
from tracerepair.recovery import InjectedCrash, PATCH_APPLIED
from tracerepair.store import TraceStore
from tracerepair.test_runner import RestrictedTestRunner


FIX_CASE_05 = """--- a/src/eventrelay/config.py
+++ b/src/eventrelay/config.py
@@ -6,6 +6,4 @@
     if value is None:
         return default
     normalized = value.strip().lower()
-    if value:
-        return True
     if normalized in {"1", "true", "yes", "on"}:
         return True
"""

SEARCH = (
    '{"kind":"tool","tool":"search_code",'
    '"arguments":{"query":"read_bool"},"reason":"locate parser"}'
)
READ = (
    '{"kind":"tool","tool":"read_file",'
    '"arguments":{"path":"src/eventrelay/config.py"},"reason":"inspect parser"}'
)
PATCH = json.dumps(
    {"kind": "patch", "unified_diff": FIX_CASE_05, "reason": "remove shortcut"}
)
BAD_PATCH = json.dumps(
    {
        "kind": "patch",
        "unified_diff": """--- a/src/eventrelay/config.py
+++ b/src/eventrelay/config.py
@@ -6,4 +6,5 @@
     if value is None:
         return default
     normalized = value.strip().lower()
+    normalized = value.lower()
     if value:
""",
        "reason": "draft overlooks whitespace handling",
    }
)
HANDOFF = '{"kind":"handoff","reason":"insufficient evidence"}'


class SequenceTransport:
    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)
        self.calls = 0
        self.payloads: list[dict[str, object]] = []

    def complete(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls += 1
        self.payloads.append(payload)
        return {
            "choices": [{"message": {"content": next(self._responses)}}],
            "usage": {"completion_tokens": 30},
        }


class DeniedTransport:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls += 1
        raise AssertionError("verification recovery must not call the model")


def _make_runtime(
    database: Path,
    workspace: Path,
    transport: object,
    *,
    create: bool,
    crash_after: str | None = None,
) -> tuple[TraceStore, LangGraphEndToEndRepairWorkflow]:
    store = TraceStore(database)
    if create:
        store.create_task(Task("graph-agent-05", "05", "false parsed as true", str(workspace)))
        store.transition("graph-agent-05", TaskStatus.READY, "ready")
        store.transition("graph-agent-05", TaskStatus.RUNNING, "started")
    tools = InstrumentedTools(
        "graph-agent-05",
        store,
        ReadOnlyRepository(workspace),
        RestrictedTestRunner(workspace),
        PatchApplier(workspace),
    )
    planner = ModelPlanner(
        transport,  # type: ignore[arg-type]
        PlannerConfig(
            max_completion_tokens=512,
            max_calls_per_task=5,
            max_total_completion_tokens=3_072,
        ),
    )
    return store, LangGraphEndToEndRepairWorkflow(
        "graph-agent-05", store, planner, tools, crash_after=crash_after
    )


def test_complete_graph_exposes_and_runs_every_repair_phase(tmp_path: Path) -> None:
    workspace = materialize_case("05", tmp_path / "case-05")
    store, workflow = _make_runtime(
        tmp_path / "trace.sqlite3",
        workspace,
        SequenceTransport([SEARCH, READ, PATCH, PATCH]),
        create=True,
    )

    graph_nodes = set(workflow.graph.get_graph().nodes)
    assert {
        "resume",
        "diagnose",
        "checkpoint_source",
        "generate_patch",
        "review_patch",
        "apply_patch",
        "run_target",
        "run_regression",
    } <= graph_nodes

    result = workflow.run("config value false must parse as False")

    assert result.task_status is TaskStatus.AWAITING_REVIEW
    assert result.action == "run_regression"
    assert result.diagnosis_turns == 2
    completed_nodes = [
        event.payload["graph_node"]
        for event in store.list_events("graph-agent-05")
        if event.event_type == "graph_node_completed"
    ]
    assert completed_nodes == [
        "diagnose",
        "diagnose",
        "checkpoint_source",
        "generate_patch",
        "review_patch",
        "apply_patch",
        "run_target",
        "run_regression",
    ]
    tools = [item["tool"] for item in store.load_checkpoint("graph-agent-05")["completed_tools"]]
    assert tools == ["search_code", "read_file", "apply_patch", "run_tests", "run_regression"]
    reviews = [
        event.payload
        for event in store.list_events("graph-agent-05")
        if event.event_type == "candidate_patch_reviewed"
    ]
    assert len(reviews) == 1
    assert reviews[0]["changed"] is False
    assert reviews[0]["draft_sha256"] == reviews[0]["reviewed_sha256"]
    assert reviews[0]["execution_authority"] is False
    store.close()


def test_graph_resume_uses_sqlite_checkpoint_and_skips_model_and_patch(tmp_path: Path) -> None:
    workspace = materialize_case("05", tmp_path / "case-05")
    database = tmp_path / "trace.sqlite3"
    first = SequenceTransport([SEARCH, READ, PATCH, PATCH])
    store, workflow = _make_runtime(
        database, workspace, first, create=True, crash_after=PATCH_APPLIED
    )

    with pytest.raises(InjectedCrash, match=PATCH_APPLIED):
        workflow.run("config value false must parse as False")
    assert store.load_checkpoint("graph-agent-05")["recovery"]["phase"] == PATCH_APPLIED
    store.close()

    store = TraceStore(database)
    store.transition("graph-agent-05", TaskStatus.READY, "operator requested resume")
    store.transition("graph-agent-05", TaskStatus.RUNNING, "resume started")
    store.close()
    denied = DeniedTransport()
    store, workflow = _make_runtime(database, workspace, denied, create=False)
    result = workflow.run("config value false must parse as False", resume=True)

    assert result.task_status is TaskStatus.AWAITING_REVIEW
    assert denied.calls == 0
    started_tools = [
        event.payload["tool"]
        for event in store.list_events("graph-agent-05")
        if event.event_type == "tool_started"
    ]
    assert started_tools.count("apply_patch") == 1
    assert started_tools[-2:] == ["run_tests", "run_regression"]
    resumed_nodes = [
        event.payload["graph_node"]
        for event in store.list_events("graph-agent-05")
        if event.event_type == "graph_node_completed"
    ]
    assert resumed_nodes[-3:] == ["resume", "run_target", "run_regression"]
    store.close()


def test_compiled_graph_has_no_langgraph_checkpointer(tmp_path: Path) -> None:
    workspace = materialize_case("05", tmp_path / "case-05")
    store, workflow = _make_runtime(
        tmp_path / "trace.sqlite3", workspace, SequenceTransport([SEARCH]), create=True
    )

    assert workflow.graph.checkpointer is None
    store.close()


def test_semantic_reviewer_can_replace_draft_before_deterministic_gates(tmp_path: Path) -> None:
    workspace = materialize_case("05", tmp_path / "case-05")
    transport = SequenceTransport([SEARCH, READ, BAD_PATCH, PATCH])
    store, workflow = _make_runtime(
        tmp_path / "trace.sqlite3", workspace, transport, create=True
    )

    result = workflow.run("config value false must parse as False")

    assert result.task_status is TaskStatus.AWAITING_REVIEW
    assert transport.calls == 4
    review = next(
        event.payload
        for event in store.list_events("graph-agent-05")
        if event.event_type == "candidate_patch_reviewed"
    )
    assert review["changed"] is True
    assert review["draft_sha256"] != review["reviewed_sha256"]
    review_system = transport.payloads[-1]["messages"][0]["content"]  # type: ignore[index]
    assert '"kind":"tool"' not in review_system
    assert '"kind":"patch"' in review_system
    assert '"kind":"handoff"' in review_system
    store.close()


def test_semantic_reviewer_handoff_never_applies_or_tests_draft(tmp_path: Path) -> None:
    workspace = materialize_case("05", tmp_path / "case-05")
    store, workflow = _make_runtime(
        tmp_path / "trace.sqlite3",
        workspace,
        SequenceTransport([SEARCH, READ, PATCH, HANDOFF]),
        create=True,
    )

    result = workflow.run("config value false must parse as False")

    assert result.task_status is TaskStatus.NEEDS_HUMAN
    assert result.action == "handoff"
    started_tools = [
        event.payload["tool"]
        for event in store.list_events("graph-agent-05")
        if event.event_type == "tool_started"
    ]
    assert started_tools == ["search_code", "read_file"]
    assert "if value:" in (workspace / "src/eventrelay/config.py").read_text(encoding="utf-8")
    store.close()
