from pathlib import Path

from evaluation.materialize import materialize_case
from tracerepair.instrumented_tools import InstrumentedTools
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
     if normalized in {\"1\", \"true\", \"yes\", \"on\"}:
         return True
"""

NON_FIXING_CASE_05 = """--- a/src/eventrelay/config.py
+++ b/src/eventrelay/config.py
@@ -6,6 +6,7 @@
     if value is None:
         return default
     normalized = value.strip().lower()
+    # Candidate accepted by policy but does not repair the behavior.
     if value:
         return True
"""


def repair_workflow(tmp_path: Path) -> tuple[TraceStore, CandidateRepairWorkflow]:
    workspace = materialize_case("05", tmp_path / "case-05")
    store = TraceStore(tmp_path / "data/trace.sqlite3")
    store.create_task(Task("repair-05", "05", "false enables retry", str(workspace)))
    store.transition("repair-05", TaskStatus.READY, "diagnosis completed")
    store.transition("repair-05", TaskStatus.RUNNING, "diagnostic test executed")
    tools = InstrumentedTools(
        "repair-05",
        store,
        ReadOnlyRepository(workspace),
        RestrictedTestRunner(workspace),
        PatchApplier(workspace),
    )
    store.transition("repair-05", TaskStatus.NEEDS_HUMAN, "candidate requested")
    return store, CandidateRepairWorkflow("repair-05", store, tools)


def test_valid_candidate_moves_to_awaiting_review(tmp_path: Path) -> None:
    store, workflow = repair_workflow(tmp_path)

    step = workflow.submit_candidate(FIX_CASE_05)

    assert step.action == "run_regression"
    assert step.task_status is TaskStatus.AWAITING_REVIEW
    assert store.get_task("repair-05").status is TaskStatus.AWAITING_REVIEW
    checkpoint = store.load_checkpoint("repair-05")
    assert [item["tool"] for item in checkpoint["completed_tools"]] == [
        "apply_patch",
        "run_tests",
        "run_regression",
    ]
    store.close()


def test_rejected_candidate_returns_to_needs_human_without_test_run(tmp_path: Path) -> None:
    store, workflow = repair_workflow(tmp_path)
    unsafe = FIX_CASE_05.replace("src/eventrelay/config.py", "tests/test_config.py")

    step = workflow.submit_candidate(unsafe)

    assert step.action == "apply_patch"
    assert step.task_status is TaskStatus.NEEDS_HUMAN
    checkpoint = store.load_checkpoint("repair-05")
    assert [item["tool"] for item in checkpoint["completed_tools"]] == ["apply_patch"]
    assert checkpoint["last_tool"]["ok"] is False
    store.close()


def test_failed_target_does_not_start_regression(tmp_path: Path) -> None:
    store, workflow = repair_workflow(tmp_path)

    step = workflow.submit_candidate(NON_FIXING_CASE_05)

    assert step.action == "run_tests"
    assert step.task_status is TaskStatus.NEEDS_HUMAN
    checkpoint = store.load_checkpoint("repair-05")
    assert [item["tool"] for item in checkpoint["completed_tools"]] == ["apply_patch", "run_tests"]
    store.close()


def test_regression_failure_returns_to_needs_human(tmp_path: Path) -> None:
    store, workflow = repair_workflow(tmp_path)
    workspace = Path(store.get_task("repair-05").workspace)
    retry_module = workspace / "src/eventrelay/retry.py"
    retry_module.write_text(
        retry_module.read_text(encoding="utf-8").replace(
            "return status_code == 429 or status_code >= 500", "return status_code >= 500"
        ),
        encoding="utf-8",
    )

    step = workflow.submit_candidate(FIX_CASE_05)

    assert step.action == "run_regression"
    assert step.task_status is TaskStatus.NEEDS_HUMAN
    checkpoint = store.load_checkpoint("repair-05")
    assert [item["tool"] for item in checkpoint["completed_tools"]] == [
        "apply_patch",
        "run_tests",
        "run_regression",
    ]
    store.close()
