import json
from pathlib import Path

from evaluation.materialize import materialize_case
from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.model_planner import ModelPlanner
from tracerepair.model_workflow import ModelGuidedWorkflow
from tracerepair.models import Task, TaskStatus
from tracerepair.patch_apply import PatchApplier
from tracerepair.read_tools import ReadOnlyRepository
from tracerepair.store import TraceStore
from tracerepair.test_runner import RestrictedTestRunner
from tracerepair.workflow import CandidateRepairWorkflow


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


class FakeTransport:
    def __init__(self, content: str) -> None:
        self.content = content

    def complete(self, _payload: dict[str, object]) -> dict[str, object]:
        return {
            "choices": [{"message": {"content": self.content}}],
            "usage": {"completion_tokens": 50},
        }


def make_workflow(tmp_path: Path, response: str) -> tuple[TraceStore, ModelGuidedWorkflow]:
    workspace = materialize_case("05", tmp_path / "case-05")
    store = TraceStore(tmp_path / "data/trace.sqlite3")
    store.create_task(Task("model-05", "05", "false parsed as true", str(workspace)))
    store.transition("model-05", TaskStatus.READY, "ready for model")
    store.transition("model-05", TaskStatus.RUNNING, "model worker attached")
    tools = InstrumentedTools(
        "model-05",
        store,
        ReadOnlyRepository(workspace),
        RestrictedTestRunner(workspace),
        PatchApplier(workspace),
    )
    repair = CandidateRepairWorkflow("model-05", store, tools)
    return store, ModelGuidedWorkflow("model-05", store, ModelPlanner(FakeTransport(response)), tools, repair)


def test_model_tool_suggestion_is_routed_to_instrumented_tool(tmp_path: Path) -> None:
    response = '{"kind":"tool","tool":"search_code","arguments":{"query":"read_bool"},"reason":"locate parser"}'
    store, workflow = make_workflow(tmp_path, response)

    step = workflow.step("target test fails when false is configured")

    assert step.action == "search_code"
    assert step.ok is True
    assert store.load_checkpoint("model-05")["last_tool"]["tool"] == "search_code"
    store.close()


def test_model_patch_still_requires_full_repair_gate(tmp_path: Path) -> None:
    response = json.dumps({"kind": "patch", "unified_diff": FIX_CASE_05, "reason": "remove truthiness branch"})
    store, workflow = make_workflow(tmp_path, response)

    step = workflow.step("target failure and source excerpt")

    assert step.action == "run_regression"
    assert step.repair_step is not None
    assert store.get_task("model-05").status is TaskStatus.AWAITING_REVIEW
    assert [item["tool"] for item in store.load_checkpoint("model-05")["completed_tools"]] == [
        "apply_patch",
        "run_tests",
        "run_regression",
    ]
    store.close()
