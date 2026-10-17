"""Run a zero-cost, two-session checkpoint recovery demonstration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.materialize import materialize_case
from tracerepair.end_to_end_workflow import EndToEndRepairWorkflow
from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.model_planner import ModelPlanner, PlannerConfig
from tracerepair.models import Task, TaskStatus
from tracerepair.patch_apply import PatchApplier
from tracerepair.read_tools import ReadOnlyRepository
from tracerepair.recovery import InjectedCrash, PATCH_APPLIED, SOURCE_READ
from tracerepair.store import TraceStore
from tracerepair.test_runner import RestrictedTestRunner
from tracerepair.version import AGENT_VERSION


FIX = """--- a/src/eventrelay/config.py
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
    {"kind": "patch", "unified_diff": FIX, "reason": "remove truthiness shortcut"}
)


class ScriptedTransport:
    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)
        self.calls = 0

    def complete(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls += 1
        return {
            "choices": [{"message": {"content": next(self._responses)}}],
            "usage": {"completion_tokens": 30},
        }


class DeniedTransport:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls += 1
        raise RuntimeError("verification-only recovery attempted a model call")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--crash-after",
        choices=(SOURCE_READ, PATCH_APPLIED),
        default=PATCH_APPLIED,
    )
    args = parser.parse_args()
    run_id = uuid4().hex[:8]
    task_id = f"recovery-demo-{run_id}"
    workspace = materialize_case(
        "05", ROOT / "workspaces" / "recovery-demo" / f"case-05-{run_id}"
    )
    database = ROOT / "data" / "recovery-demo.sqlite3"
    store = TraceStore(database)
    store.create_task(Task(task_id, "05", "false parsed as true", str(workspace)))
    store.append_event(
        task_id,
        "run_metadata",
        {
            "agent_version": AGENT_VERSION,
            "model": "scripted-offline",
            "demo": "checkpoint-recovery",
        },
    )
    store.transition(task_id, TaskStatus.READY, "recovery demo workspace created")
    store.transition(task_id, TaskStatus.RUNNING, "recovery demo phase one started")
    first_responses = [SEARCH, READ] + ([PATCH] if args.crash_after == PATCH_APPLIED else [])
    first_transport = ScriptedTransport(first_responses)
    first = _workflow(task_id, store, workspace, first_transport, args.crash_after)
    try:
        first.run("config value false must parse as False")
    except InjectedCrash:
        pass
    else:
        raise RuntimeError("fault injection did not interrupt phase one")
    phase_one_tools = _started_tools(store, task_id)
    phase_one_calls = _model_calls(store, task_id)
    store.close()

    # Reopening SQLite and rebuilding every runtime dependency models a fresh process.
    store = TraceStore(database)
    store.transition(task_id, TaskStatus.READY, "operator requested checkpoint resume")
    store.transition(task_id, TaskStatus.RUNNING, "recovery demo phase two started")
    store.append_event(
        task_id,
        "resume_requested",
        {"previous_status": TaskStatus.INTERRUPTED.value},
    )
    second_transport: ScriptedTransport | DeniedTransport
    second_transport = (
        ScriptedTransport([PATCH])
        if args.crash_after == SOURCE_READ
        else DeniedTransport()
    )
    second = _workflow(task_id, store, workspace, second_transport, None)
    result = second.run("config value false must parse as False", resume=True)
    final_tools = _started_tools(store, task_id)
    if len(final_tools) != len(set(final_tools)):
        raise RuntimeError(f"a completed tool was repeated: {final_tools}")
    if result.task_status is not TaskStatus.AWAITING_REVIEW:
        raise RuntimeError(f"recovery did not reach review: {result.detail}")
    skipped = [
        event.payload
        for event in store.list_events(task_id)
        if event.event_type == "recovery_step_skipped"
    ]
    print("Checkpoint recovery demo completed.")
    print(f"Task: {task_id}")
    print(f"Crash point: {args.crash_after}")
    print(f"Phase 1 completed tools: {phase_one_tools}")
    print(f"Phase 1 model calls: {phase_one_calls}")
    print(f"Resume skipped completed work: {skipped}")
    print(f"Final tool sequence: {final_tools}")
    print(f"Resume model calls: {second_transport.calls}")
    print(f"Final status: {result.task_status.value}; detail: {result.detail}")
    print(f"Trace database: data/recovery-demo.sqlite3 (task {task_id})")
    store.close()


def _workflow(
    task_id: str,
    store: TraceStore,
    workspace: Path,
    transport: object,
    crash_after: str | None,
) -> EndToEndRepairWorkflow:
    tools = InstrumentedTools(
        task_id,
        store,
        ReadOnlyRepository(workspace),
        RestrictedTestRunner(workspace),
        PatchApplier(workspace),
    )
    planner = ModelPlanner(
        transport,  # type: ignore[arg-type]
        PlannerConfig(
            max_completion_tokens=512,
            max_calls_per_task=4,
            max_total_completion_tokens=2_048,
        ),
    )
    return EndToEndRepairWorkflow(
        task_id, store, planner, tools, crash_after=crash_after
    )


def _started_tools(store: TraceStore, task_id: str) -> list[str]:
    return [
        str(event.payload["tool"])
        for event in store.list_events(task_id)
        if event.event_type == "tool_started"
    ]


def _model_calls(store: TraceStore, task_id: str) -> int:
    budget = store.load_checkpoint(task_id).get("model_budget", {})
    return int(budget.get("calls", 0)) if isinstance(budget, dict) else 0


if __name__ == "__main__":
    main()
