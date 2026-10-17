"""A resumable, deterministic diagnostic workflow used before any LLM is added."""

from dataclasses import dataclass

from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.models import TaskStatus
from tracerepair.store import TraceStore


_CASE_SELECTORS = {
    "01": "tests/test_repair_targets.py::test_case_01_uses_event_id_for_idempotency",
    "02": "tests/test_repair_targets.py::test_case_02_normalizes_naive_timestamp",
    "03": "tests/test_repair_targets.py::test_case_03_respects_retry_budget",
    "04": "tests/test_repair_targets.py::test_case_04_retries_rate_limits",
    "05": "tests/test_repair_targets.py::test_case_05_parses_false_as_false",
    "06": "tests/test_repair_targets.py::test_case_06_rejects_unknown_input",
    "07": "tests/test_repair_targets.py::test_case_07_cursor_does_not_repeat",
    "08": "tests/test_repair_targets.py::test_case_08_failed_event_can_be_redelivered",
    "09": "tests/test_repair_targets.py::test_case_09_compares_retention_in_milliseconds",
    "10": "tests/test_repair_targets.py::test_case_10_isolates_batch_validation",
}


def case_selector(case_id: str) -> str:
    try:
        return _CASE_SELECTORS[case_id]
    except KeyError as error:
        raise ValueError(f"unknown case selector: {case_id}") from error


@dataclass(frozen=True)
class WorkflowStep:
    action: str
    task_status: TaskStatus
    detail: str


class DeterministicWorkflow:
    """Execute a small, restart-safe diagnostic sequence.

    The sequence is deliberately fixed: map, search, inspect processor, test,
    then hand off. It is a safe integration harness for tool and persistence
    contracts, not a replacement for the eventual model-driven planner.
    """

    def __init__(self, task_id: str, store: TraceStore, tools: InstrumentedTools) -> None:
        self._task_id = task_id
        self._store = store
        self._tools = tools

    def step(self) -> WorkflowStep:
        task = self._store.get_task(self._task_id)
        if task.status is TaskStatus.READY:
            self._store.transition(self._task_id, TaskStatus.RUNNING, "deterministic workflow started")
            task = self._store.get_task(self._task_id)
        if task.status is not TaskStatus.RUNNING:
            return WorkflowStep("stop", task.status, "task is not runnable")

        completed = self._store.load_checkpoint(self._task_id).get("completed_tools", [])
        completed_names = [item["tool"] for item in completed]
        if "repo_map" not in completed_names:
            result = self._tools.repo_map()
            return WorkflowStep("repo_map", TaskStatus.RUNNING, f"mapped {len(result.data or [])} files")
        if "search_code" not in completed_names:
            result = self._tools.search_code("event")
            return WorkflowStep("search_code", TaskStatus.RUNNING, f"found {len(result.data or [])} matches")
        if "read_file" not in completed_names:
            result = self._tools.read_file("src/eventrelay/processor.py", 1, 200)
            detail = "read processor source" if result.ok else "processor source unavailable"
            return WorkflowStep("read_file", TaskStatus.RUNNING, detail)
        if "run_tests" not in completed_names:
            try:
                selector = case_selector(task.case_id)
            except ValueError:
                self._store.transition(self._task_id, TaskStatus.NEEDS_HUMAN, "unknown case selector")
                return WorkflowStep("stop", TaskStatus.NEEDS_HUMAN, "case has no target selector")
            result = self._tools.run_tests(selector)
            outcome = "passed" if result.ok else result.error_code or "failed"
            self._store.transition(
                self._task_id,
                TaskStatus.NEEDS_HUMAN,
                "deterministic diagnosis complete; no patch generation is permitted",
            )
            return WorkflowStep("run_tests", TaskStatus.NEEDS_HUMAN, f"target test {outcome}")

        self._store.transition(self._task_id, TaskStatus.NEEDS_HUMAN, "diagnostic steps already complete")
        return WorkflowStep("stop", TaskStatus.NEEDS_HUMAN, "awaiting a future planner")

    def run_to_stop(self, max_steps: int = 5) -> list[WorkflowStep]:
        if not 1 <= max_steps <= 10:
            raise ValueError("max_steps must be between 1 and 10")
        steps: list[WorkflowStep] = []
        for _ in range(max_steps):
            step = self.step()
            steps.append(step)
            if step.task_status is not TaskStatus.RUNNING:
                break
        return steps


class CandidateRepairWorkflow:
    """Apply one externally supplied candidate diff, then verify its target test.

    The candidate is intentionally external to this class: in the current phase
    it may come from a human; later it may come from a model-backed planner.
    """

    def __init__(self, task_id: str, store: TraceStore, tools: InstrumentedTools) -> None:
        self._task_id = task_id
        self._store = store
        self._tools = tools

    def submit_candidate(self, unified_diff: str) -> WorkflowStep:
        task = self._store.get_task(self._task_id)
        if task.status is TaskStatus.NEEDS_HUMAN:
            self._store.transition(self._task_id, TaskStatus.READY, "operator supplied candidate diff")
            task = self._store.get_task(self._task_id)
        if task.status is TaskStatus.READY:
            self._store.transition(self._task_id, TaskStatus.RUNNING, "candidate repair started")
            task = self._store.get_task(self._task_id)
        if task.status is not TaskStatus.RUNNING:
            return WorkflowStep("stop", task.status, "task cannot accept a candidate diff")

        applied = self._tools.apply_patch(unified_diff)
        if not applied.ok:
            self._store.transition(
                self._task_id,
                TaskStatus.NEEDS_HUMAN,
                f"candidate patch rejected: {applied.error_code}",
            )
            return WorkflowStep("apply_patch", TaskStatus.NEEDS_HUMAN, applied.error_code or "rejected")

        try:
            selector = case_selector(task.case_id)
        except ValueError:
            self._store.transition(self._task_id, TaskStatus.NEEDS_HUMAN, "unknown case selector")
            return WorkflowStep("stop", TaskStatus.NEEDS_HUMAN, "case has no target selector")
        result = self._tools.run_tests(selector)
        if result.ok:
            regression = self._tools.run_regression()
            if not regression.ok:
                self._store.transition(
                    self._task_id,
                    TaskStatus.NEEDS_HUMAN,
                    f"candidate patch failed regression: {regression.error_code}",
                )
                return WorkflowStep(
                    "run_regression", TaskStatus.NEEDS_HUMAN, regression.error_code or "failed"
                )
            self._store.transition(
                self._task_id,
                TaskStatus.AWAITING_REVIEW,
                "candidate patch passed target and regression tests; human review required",
            )
            return WorkflowStep("run_regression", TaskStatus.AWAITING_REVIEW, "all tests passed")
        self._store.transition(
            self._task_id,
            TaskStatus.NEEDS_HUMAN,
            f"candidate patch failed target test: {result.error_code}",
        )
        return WorkflowStep("run_tests", TaskStatus.NEEDS_HUMAN, result.error_code or "failed")
