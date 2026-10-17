"""Run a zero-cost cross-repository repair through the configured adapter."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tracerepair.end_to_end_workflow import EndToEndRepairWorkflow
from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.model_planner import ModelPlanner, PlannerConfig
from tracerepair.models import Task, TaskStatus
from tracerepair.patch_apply import PatchApplier
from tracerepair.patch_policy import PatchPolicy
from tracerepair.read_tools import ReadOnlyRepository
from tracerepair.repository_task import RepositoryTaskSpec, materialize_repository
from tracerepair.store import TraceStore
from tracerepair.test_runner import RestrictedTestRunner


FIX = """--- a/src/minimath/pricing.py
+++ b/src/minimath/pricing.py
@@ -6,4 +6,4 @@
         raise ValueError("total must not be negative")
     if not 0 <= rate <= 1:
         raise ValueError("rate must be between zero and one")
-    return round(total * rate, 2)
+    return round(total * (1 - rate), 2)
"""


class ScriptedTransport:
    """Deterministic responses prove plumbing without spending API tokens."""

    def __init__(self) -> None:
        self._responses = iter(
            [
                '{"kind":"tool","tool":"search_code","arguments":{"query":"def apply_discount"},"reason":"locate"}',
                '{"kind":"tool","tool":"read_file","arguments":{"path":"src/minimath/pricing.py"},"reason":"inspect"}',
                json.dumps({"kind": "patch", "unified_diff": FIX, "reason": "correct formula"}),
            ]
        )

    def complete(self, payload: dict[str, object]) -> dict[str, object]:
        return {
            "choices": [{"message": {"content": next(self._responses)}}],
            "usage": {"completion_tokens": 30},
        }


def main() -> None:
    spec = RepositoryTaskSpec.load(ROOT / "examples" / "tasks" / "mini-repo.json")
    run_id = uuid4().hex[:8]
    task_id = f"generic-demo-{run_id}"
    workspace = materialize_repository(
        spec, ROOT / "workspaces" / "generic-demo" / f"{spec.name}-{run_id}"
    )
    store = TraceStore(ROOT / "data" / "generic-demo.sqlite3")
    store.create_task(Task(task_id, f"repo-{spec.name}", spec.issue, str(workspace)))
    store.transition(task_id, TaskStatus.READY, "configured repository copied")
    store.transition(task_id, TaskStatus.RUNNING, "cross-repository demo started")
    runner = RestrictedTestRunner(
        workspace,
        allowed_targets=(spec.target_test,),
        regression_selector=spec.regression_suite,
        pythonpath=spec.pythonpath,
        timeout_seconds=spec.timeout_seconds,
    )
    before = runner.run_tests(spec.target_test)
    if before.ok:
        raise RuntimeError("example target unexpectedly passed before repair")
    tools = InstrumentedTools(
        task_id,
        store,
        ReadOnlyRepository(workspace, allowed_roots=spec.source_allowlist),
        runner,
        PatchApplier(workspace, PatchPolicy(allowed_roots=spec.source_allowlist)),
    )
    planner = ModelPlanner(
        ScriptedTransport(),
        PlannerConfig(
            max_completion_tokens=512,
            max_calls_per_task=4,
            max_total_completion_tokens=2_048,
        ),
    )
    result = EndToEndRepairWorkflow(
        task_id,
        store,
        planner,
        tools,
        target_selector=spec.target_test,
        allowed_source_roots=spec.source_allowlist,
    ).run(spec.issue, diagnostic_queries=spec.diagnostic_queries)
    tools_started = [
        str(event.payload["tool"])
        for event in store.list_events(task_id)
        if event.event_type == "tool_started"
    ]
    print("Configured repository demo completed.")
    print(f"Repository task: {spec.name}")
    print(f"Initial target: {before.error_code}")
    print(f"Tool sequence: {tools_started}")
    print(f"Final status: {result.task_status.value}; detail: {result.detail}")
    print(f"Trace database: data/generic-demo.sqlite3 (task {task_id})")
    store.close()
    if result.task_status is not TaskStatus.AWAITING_REVIEW:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
