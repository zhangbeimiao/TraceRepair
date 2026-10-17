"""Run one low-budget, read-only model decision on EventRelay case 05.

This is intentionally a probe, not an autonomous repair run: one model request
and at most one repository read. Patches and test runs are never executed here.
"""

from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.materialize import materialize_case
from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.model_planner import BailianChatTransport, ModelPlanner, PlannerConfig, PlannerError
from tracerepair.models import Task, TaskStatus
from tracerepair.read_tools import ReadOnlyRepository
from tracerepair.store import TraceStore
from tracerepair.test_runner import RestrictedTestRunner


_READ_ONLY_TOOLS = {"repo_map", "search_code", "read_file"}


def main() -> None:
    run_id = uuid4().hex[:8]
    workspace = materialize_case("05", ROOT / "workspaces" / "model-probe" / f"case-05-{run_id}")
    store = TraceStore(ROOT / "data" / "model-probe.sqlite3")
    task_id = f"model-probe-{run_id}"
    store.create_task(Task(task_id, "05", "false configuration is interpreted as true", str(workspace)))
    store.transition(task_id, TaskStatus.READY, "probe workspace created")
    store.transition(task_id, TaskStatus.RUNNING, "read-only probe started")
    tools = InstrumentedTools(
        task_id,
        store,
        ReadOnlyRepository(workspace),
        RestrictedTestRunner(workspace),
    )
    planner = ModelPlanner(
        BailianChatTransport(),
        PlannerConfig(max_completion_tokens=128, max_calls_per_task=1, max_total_completion_tokens=128),
    )
    evidence = """Task: EventRelay case 05. The target behavior is that config value 'false' parses as False.
At the start of diagnosis, choose exactly one safe next action. Prefer gathering evidence before proposing a patch.
Allowed tools are repo_map, search_code, read_file, and run_tests. Do not propose a patch yet."""
    try:
        plan = planner.suggest(task_id, store, evidence)
    except PlannerError as error:
        print(f"Model decision probe failed safely: {error}")
        raise SystemExit(1) from error

    try:
        if plan.kind != "tool" or plan.tool not in _READ_ONLY_TOOLS:
            print(f"Model selected {plan.kind}:{plan.tool}; probe policy refused to execute it.")
            return
        if plan.tool == "repo_map":
            result = tools.repo_map()
        elif plan.tool == "search_code":
            query = plan.arguments.get("query")
            if not isinstance(query, str) or not query.strip():
                print("Model supplied an invalid search query; nothing executed.")
                return
            result = tools.search_code(query)
        else:
            path = plan.arguments.get("path")
            if not isinstance(path, str):
                print("Model supplied an invalid read path; nothing executed.")
                return
            result = tools.read_file(path)
        print("Model decision probe completed.")
        print(f"Selected action: {plan.tool}")
        print(f"Read-only tool succeeded: {result.ok}")
        print(f"Model output tokens: {plan.completion_tokens} (limit: 128)")
        print("Trace: model plan, tool lifecycle, and checkpoint were persisted.")
    finally:
        store.close()
    print(f"Trace database: data/model-probe.sqlite3 (task {task_id})")


if __name__ == "__main__":
    main()
