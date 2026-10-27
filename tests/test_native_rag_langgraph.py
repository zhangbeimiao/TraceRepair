import json
from pathlib import Path

from evaluation.materialize import materialize_case
from tracerepair.code_retrieval import CodeIndex, CodeRagRetriever, HashEmbeddingProvider
from tracerepair.function_calling import NativeFunctionPlanner
from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.langgraph_end_to_end import LangGraphEndToEndRepairWorkflow
from tracerepair.model_planner import PlannerConfig
from tracerepair.models import Task, TaskStatus
from tracerepair.patch_apply import PatchApplier
from tracerepair.read_tools import ReadOnlyRepository
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


def call(name: str, arguments: dict[str, object], index: int) -> dict[str, object]:
    return {
        "id": f"call-{index}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


class NativeSequenceTransport:
    def __init__(self, calls: list[dict[str, object]]) -> None:
        self._calls = iter(calls)
        self.payloads: list[dict[str, object]] = []

    def complete(self, payload: dict[str, object]) -> dict[str, object]:
        self.payloads.append(payload)
        return {
            "choices": [{"message": {"content": None, "tool_calls": [next(self._calls)]}}],
            "usage": {"completion_tokens": 25},
        }


def test_native_functions_and_rag_complete_the_existing_test_gated_graph(tmp_path: Path) -> None:
    workspace = materialize_case("05", tmp_path / "case-05")
    store = TraceStore(tmp_path / "trace.sqlite3")
    store.create_task(Task("native-rag-05", "05", "false parsed as true", str(workspace)))
    store.transition("native-rag-05", TaskStatus.READY, "ready")
    store.transition("native-rag-05", TaskStatus.RUNNING, "started")
    tools = InstrumentedTools(
        "native-rag-05",
        store,
        ReadOnlyRepository(workspace),
        RestrictedTestRunner(workspace),
        PatchApplier(workspace),
    )
    transport = NativeSequenceTransport(
        [
            call(
                "read_file",
                {"path": "src/eventrelay/config.py", "start_line": 1, "end_line": 200},
                1,
            ),
            call("propose_patch", {"unified_diff": FIX_CASE_05, "reason": "remove shortcut"}, 2),
            call("propose_patch", {"unified_diff": FIX_CASE_05, "reason": "reviewed"}, 3),
        ]
    )
    planner = NativeFunctionPlanner(
        transport,
        PlannerConfig(
            max_completion_tokens=256,
            max_calls_per_task=4,
            max_total_completion_tokens=1024,
        ),
    )
    provider = HashEmbeddingProvider(64)
    index_path = Path("D:/AI-Agent-Intern/TraceRepair/.tmp") / f"native-rag-{tmp_path.name}.sqlite3"
    with CodeIndex(index_path) as index:
        index.build(workspace, allowed_roots=("src/eventrelay",), embedding_provider=provider)
        retriever = CodeRagRetriever(index, embedding_provider=provider, limit=3)
        result = LangGraphEndToEndRepairWorkflow(
            "native-rag-05",
            store,
            planner,  # type: ignore[arg-type]
            tools,
            rag_retriever=retriever,
        ).run("config value false must parse as False", diagnostic_queries=("read_bool",))

    assert result.task_status is TaskStatus.AWAITING_REVIEW
    assert result.action == "run_regression"
    assert result.diagnosis_turns == 1
    model_events = [
        event for event in store.list_events("native-rag-05") if event.event_type == "model_plan_recorded"
    ]
    assert len(model_events) == 3
    assert [event.payload["stage"] for event in model_events] == [
        "diagnosis",
        "patch_generation",
        "patch_review",
    ]
    assert all(event.payload["native_function_calling"] is True for event in model_events)
    rag_event = next(
        event
        for event in store.list_events("native-rag-05")
        if event.event_type == "rag_retrieval_completed"
    )
    assert rag_event.payload["execution_authority"] is False
    assert any(hit["path"] == "src/eventrelay/config.py" for hit in rag_event.payload["hits"])
    assert "DASHSCOPE_API_KEY" not in str(rag_event.payload)
    diagnosis_tools = {
        item["function"]["name"] for item in transport.payloads[0]["tools"]
    }
    assert diagnosis_tools == {"repo_map", "search_code", "read_file", "handoff"}
    assert "propose_patch" not in diagnosis_tools
    store.close()
