"""Run one bounded end-to-end repair attempt on an allowlisted evaluation case."""

import argparse
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.materialize import load_case, materialize_case
from tracerepair.end_to_end_workflow import EndToEndRepairWorkflow
from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.model_planner import BailianChatTransport, ModelPlanner, PlannerConfig, PlannerError
from tracerepair.models import Task, TaskStatus
from tracerepair.patch_apply import PatchApplier
from tracerepair.read_tools import ReadOnlyRepository
from tracerepair.store import TraceStore
from tracerepair.test_runner import RestrictedTestRunner
from tracerepair.version import AGENT_VERSION, MODEL_ID
from tracerepair.workflow import case_selector


DEVELOPMENT_CASES = ("01", "03", "05", "07", "10")
LOCKED_CASES = ("02", "04", "06", "08", "09")
DIAGNOSTIC_QUERIES = {
    "01": ("def seen",),
    "02": ("def parse_event",),
    "03": ("def retry",),
    "04": ("def is_retryable_status",),
    "05": ("def read_bool",),
    "06": ("def parse_event",),
    "07": ("def list_after",),
    "08": ("def handle",),
    "09": ("def expired_event_ids",),
    "10": ("def handle_batch",),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=DEVELOPMENT_CASES + LOCKED_CASES, default="05")
    parser.add_argument(
        "--evaluation-split",
        choices=("development", "locked"),
        default="development",
        help="locked cases must be invoked explicitly by the blind-evaluation runner",
    )
    arguments = parser.parse_args()
    case_id = arguments.case
    case = load_case(case_id)
    if case["split"] != arguments.evaluation_split:
        parser.error(
            f"case {case_id} belongs to the {case['split']} split, "
            f"not {arguments.evaluation_split}"
        )
    issue = str(case["issue"])
    selector = case_selector(case_id)
    diagnostic_queries = DIAGNOSTIC_QUERIES[case_id]
    run_id = uuid4().hex[:8]
    workspace = materialize_case(
        case_id,
        ROOT / "workspaces" / "model-agent" / f"case-{case_id}-{run_id}",
    )
    store = TraceStore(ROOT / "data" / "model-agent.sqlite3")
    task_id = f"model-agent-{case_id}-{run_id}"
    store.create_task(Task(task_id, case_id, issue, str(workspace)))
    store.append_event(
        task_id,
        "run_metadata",
        {
            "agent_version": AGENT_VERSION,
            "model": MODEL_ID,
            "case_name": str(case["name"]),
            "evaluation_split": str(case["split"]),
            "target_selector": selector,
            "diagnostic_queries": list(diagnostic_queries),
            "max_model_calls": 4,
            "max_completion_tokens": 2_048,
        },
    )
    store.transition(task_id, TaskStatus.READY, "end-to-end workspace created")
    store.transition(task_id, TaskStatus.RUNNING, "end-to-end model workflow started")
    tools = InstrumentedTools(
        task_id,
        store,
        ReadOnlyRepository(workspace),
        RestrictedTestRunner(workspace),
        PatchApplier(workspace),
    )
    planner = ModelPlanner(
        BailianChatTransport(),
        PlannerConfig(
            max_completion_tokens=512,
            max_calls_per_task=4,
            max_total_completion_tokens=2_048,
        ),
    )
    try:
        task_evidence = f"{issue} Failing target: {selector}."
        result = EndToEndRepairWorkflow(task_id, store, planner, tools).run(
            task_evidence,
            diagnostic_queries=diagnostic_queries,
        )
        budget = store.load_checkpoint(task_id).get("model_budget", {})
        print("End-to-end repair run completed.")
        print(f"Agent version: {AGENT_VERSION}; case: {case_id} ({case['name']})")
        print(f"Diagnosis turns: {result.diagnosis_turns}/3")
        print(
            f"Model usage: calls={budget.get('calls', 0)}/4, "
            f"output_tokens={result.completion_tokens}/2048"
        )
        print(f"Verification action: {result.action}")
        print(f"Final task status: {result.task_status.value}")
        print(f"Detail: {result.detail}")
        print(f"Trace database: data/model-agent.sqlite3 (task {task_id})")
    except PlannerError as error:
        if store.get_task(task_id).status is TaskStatus.RUNNING:
            store.transition(task_id, TaskStatus.NEEDS_HUMAN, f"planner stopped safely: {error}")
        print(f"End-to-end repair stopped safely: {error}")
        print(f"Trace database: data/model-agent.sqlite3 (task {task_id})")
        raise SystemExit(1) from error
    finally:
        store.close()


if __name__ == "__main__":
    main()
