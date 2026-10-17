import json
from pathlib import Path

import pytest

from tracerepair.end_to_end_workflow import EndToEndRepairWorkflow
from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.model_planner import ModelPlanner, PlannerConfig
from tracerepair.models import Task, TaskStatus
from tracerepair.patch_apply import PatchApplier
from tracerepair.patch_policy import PatchPolicy
from tracerepair.read_tools import ReadOnlyRepository
from tracerepair.recovery import InjectedCrash, PATCH_APPLIED
from tracerepair.repository_task import RepositoryTaskSpec, materialize_repository
from tracerepair.store import TraceStore
from tracerepair.test_runner import RestrictedTestRunner


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "examples" / "tasks" / "mini-repo.json"
FIX = """--- a/src/minimath/pricing.py
+++ b/src/minimath/pricing.py
@@ -6,4 +6,4 @@
         raise ValueError("total must not be negative")
     if not 0 <= rate <= 1:
         raise ValueError("rate must be between zero and one")
-    return round(total * rate, 2)
+    return round(total * (1 - rate), 2)
"""


class SequenceTransport:
    def __init__(self) -> None:
        self.responses = iter(
            [
                '{"kind":"tool","tool":"search_code","arguments":{"query":"def apply_discount"},"reason":"locate"}',
                '{"kind":"tool","tool":"read_file","arguments":{"path":"src/minimath/pricing.py"},"reason":"inspect"}',
                json.dumps({"kind": "patch", "unified_diff": FIX, "reason": "correct formula"}),
            ]
        )

    def complete(self, payload: dict[str, object]) -> dict[str, object]:
        return {
            "choices": [{"message": {"content": next(self.responses)}}],
            "usage": {"completion_tokens": 30},
        }


class DeniedTransport:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls += 1
        raise AssertionError("patch-applied resume must not call the model")


def _workflow(
    task_id: str,
    store: TraceStore,
    workspace: Path,
    spec: RepositoryTaskSpec,
    transport: object,
    *,
    crash_after: str | None = None,
) -> tuple[RestrictedTestRunner, EndToEndRepairWorkflow]:
    runner = RestrictedTestRunner(
        workspace,
        allowed_targets=(spec.target_test,),
        regression_selector=spec.regression_suite,
        pythonpath=spec.pythonpath,
    )
    tools = InstrumentedTools(
        task_id,
        store,
        ReadOnlyRepository(workspace, allowed_roots=spec.source_allowlist),
        runner,
        PatchApplier(workspace, PatchPolicy(allowed_roots=spec.source_allowlist)),
    )
    planner = ModelPlanner(
        transport,  # type: ignore[arg-type]
        PlannerConfig(
            max_completion_tokens=512,
            max_calls_per_task=4,
            max_total_completion_tokens=2_048,
        ),
    )
    return runner, EndToEndRepairWorkflow(
        task_id,
        store,
        planner,
        tools,
        target_selector=spec.target_test,
        allowed_source_roots=spec.source_allowlist,
        crash_after=crash_after,
    )


def test_cross_repository_repair_reaches_review(tmp_path: Path) -> None:
    spec = RepositoryTaskSpec.load(CONFIG)
    workspace = materialize_repository(spec, tmp_path / "workspace")
    store = TraceStore(tmp_path / "trace.sqlite3")
    task_id = "generic-mini-repo"
    store.create_task(Task(task_id, "repo-mini", spec.issue, str(workspace)))
    store.transition(task_id, TaskStatus.READY, "ready")
    store.transition(task_id, TaskStatus.RUNNING, "started")
    runner, workflow = _workflow(task_id, store, workspace, spec, SequenceTransport())
    assert runner.run_tests(spec.target_test).ok is False

    result = workflow.run(spec.issue, diagnostic_queries=spec.diagnostic_queries)

    assert result.task_status is TaskStatus.AWAITING_REVIEW
    assert runner.run_regression().ok is True
    assert [
        event.payload["tool"]
        for event in store.list_events(task_id)
        if event.event_type == "tool_started"
    ] == ["search_code", "read_file", "apply_patch", "run_tests", "run_regression"]
    store.close()


def test_generic_repository_resume_skips_model_after_patch(tmp_path: Path) -> None:
    spec = RepositoryTaskSpec.load(CONFIG)
    workspace = materialize_repository(spec, tmp_path / "workspace")
    database = tmp_path / "trace.sqlite3"
    task_id = "generic-resume"
    store = TraceStore(database)
    store.create_task(Task(task_id, "repo-mini", spec.issue, str(workspace)))
    store.transition(task_id, TaskStatus.READY, "ready")
    store.transition(task_id, TaskStatus.RUNNING, "started")
    _, workflow = _workflow(
        task_id,
        store,
        workspace,
        spec,
        SequenceTransport(),
        crash_after=PATCH_APPLIED,
    )

    with pytest.raises(InjectedCrash, match=PATCH_APPLIED):
        workflow.run(spec.issue, diagnostic_queries=spec.diagnostic_queries)
    store.close()

    store = TraceStore(database)
    store.transition(task_id, TaskStatus.READY, "operator resume")
    store.transition(task_id, TaskStatus.RUNNING, "resume started")
    denied = DeniedTransport()
    _, resumed = _workflow(task_id, store, workspace, spec, denied)
    result = resumed.run(spec.issue, resume=True)

    assert result.task_status is TaskStatus.AWAITING_REVIEW
    assert denied.calls == 0
    assert [
        event.payload["tool"]
        for event in store.list_events(task_id)
        if event.event_type == "tool_started"
    ] == ["search_code", "read_file", "apply_patch", "run_tests", "run_regression"]
    store.close()
