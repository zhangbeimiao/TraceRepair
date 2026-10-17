"""Generate one small candidate diff, then run the complete controlled repair gate."""

import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.materialize import materialize_case
from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.model_planner import BailianChatTransport, ModelPlanner, PlannerConfig, PlannerError
from tracerepair.models import Task, TaskStatus
from tracerepair.patch_apply import PatchApplier
from tracerepair.read_tools import ReadOnlyRepository
from tracerepair.store import TraceStore
from tracerepair.test_runner import RestrictedTestRunner
from tracerepair.workflow import CandidateRepairWorkflow


def main() -> None:
    run_id = uuid4().hex[:8]
    workspace = materialize_case("05", ROOT / "workspaces" / "model-patch" / f"case-05-{run_id}")
    store = TraceStore(ROOT / "data" / "model-patch.sqlite3")
    task_id = f"model-patch-{run_id}"
    store.create_task(Task(task_id, "05", "false configuration is interpreted as true", str(workspace)))
    store.transition(task_id, TaskStatus.READY, "patch probe workspace created")
    store.transition(task_id, TaskStatus.RUNNING, "patch generation started")
    tools = InstrumentedTools(
        task_id,
        store,
        ReadOnlyRepository(workspace),
        RestrictedTestRunner(workspace),
        PatchApplier(workspace),
    )
    source = (workspace / "src" / "eventrelay" / "config.py").read_text(encoding="utf-8")
    evidence = (
        "Task: repair case 05. Environment value 'false' must parse as False.\n"
        "Confirmed failing file: src/eventrelay/config.py\n"
        "Return the smallest unified diff against that exact path. Do not edit tests.\n"
        "Copy every context and removed line exactly from Source; include at least "
        "three unchanged context lines around the edit and use correct 1-based hunk line numbers.\n"
        f"Source:\n{source}"
    )
    planner = ModelPlanner(
        BailianChatTransport(),
        PlannerConfig(max_completion_tokens=512, max_calls_per_task=1, max_total_completion_tokens=512),
    )
    try:
        plan = planner.suggest(task_id, store, evidence, allowed_tools=set(), allow_patch=True)
        if plan.kind != "patch":
            store.transition(task_id, TaskStatus.NEEDS_HUMAN, "model declined to produce a patch")
            print(f"Patch probe handed off safely: {plan.reason}")
            return
        store.transition(task_id, TaskStatus.NEEDS_HUMAN, "model candidate requires controlled verification")
        result = CandidateRepairWorkflow(task_id, store, tools).submit_candidate(plan.unified_diff or "")
        print("Model patch probe completed.")
        print(f"Model output tokens: {plan.completion_tokens}/512")
        print(f"Verification action: {result.action}")
        print(f"Final task status: {result.task_status.value}")
        print(f"Detail: {result.detail}")
        print(f"Trace database: data/model-patch.sqlite3 (task {task_id})")
    except PlannerError as error:
        if store.get_task(task_id).status is TaskStatus.RUNNING:
            store.transition(task_id, TaskStatus.NEEDS_HUMAN, f"patch planner stopped safely: {error}")
        print(f"Patch probe stopped safely: {error}")
        raise SystemExit(1) from error
    finally:
        store.close()


if __name__ == "__main__":
    main()
