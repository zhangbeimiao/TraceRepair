"""A resumable, deterministic diagnostic workflow used before any LLM is added."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.models import TaskStatus
from tracerepair.recovery import (
    PATCH_APPLIED,
    TARGET_PASSED,
    RecoveryError,
    inject_crash_if_requested,
    mark_recovery_phase,
    recovery_state,
)
from tracerepair.repository_task import is_allowed_source_path
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

    def __init__(
        self,
        task_id: str,
        store: TraceStore,
        tools: InstrumentedTools,
        *,
        target_selector: str | None = None,
        allowed_source_roots: tuple[str, ...] = ("src/eventrelay",),
        crash_after: str | None = None,
    ) -> None:
        self._task_id = task_id
        self._store = store
        self._tools = tools
        self._target_selector = target_selector
        self._allowed_source_roots = allowed_source_roots
        self._crash_after = crash_after

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

        mark_recovery_phase(self._task_id, self._store, PATCH_APPLIED)
        inject_crash_if_requested(
            self._task_id,
            self._store,
            configured_point=self._crash_after,
            reached_point=PATCH_APPLIED,
        )

        return self._verify_from_checkpoint(task.case_id)

    def resume(self) -> WorkflowStep:
        """Continue after a durable patch checkpoint without applying it again."""

        task = self._store.get_task(self._task_id)
        if task.status is not TaskStatus.RUNNING:
            return WorkflowStep("stop", task.status, "task is not runnable")
        try:
            phase = recovery_state(self._store.load_checkpoint(self._task_id)).get("phase")
        except RecoveryError as error:
            return self._fail_resume(str(error))
        if phase not in {PATCH_APPLIED, TARGET_PASSED}:
            return self._fail_resume("checkpoint is not ready for verification recovery")
        applied = self._latest_tool_result("apply_patch")
        if applied is None or applied.get("ok") is not True:
            return self._fail_resume("checkpoint has no successful patch application")
        integrity_error = self._verify_applied_files(applied)
        if integrity_error is not None:
            return self._fail_resume(integrity_error)
        self._store.append_event(
            self._task_id,
            "recovery_step_skipped",
            {"tool": "apply_patch", "reason": "verified completed tool result"},
        )
        return self._verify_from_checkpoint(task.case_id)

    def _verify_from_checkpoint(self, case_id: str) -> WorkflowStep:
        if self._target_selector is not None:
            selector = self._target_selector
        else:
            try:
                selector = case_selector(case_id)
            except ValueError:
                self._store.transition(self._task_id, TaskStatus.NEEDS_HUMAN, "unknown case selector")
                return WorkflowStep("stop", TaskStatus.NEEDS_HUMAN, "case has no target selector")

        target = self._latest_tool_result("run_tests")
        if target is None:
            result = self._tools.run_tests(selector)
            if not result.ok:
                self._store.transition(
                    self._task_id,
                    TaskStatus.NEEDS_HUMAN,
                    f"candidate patch failed target test: {result.error_code}",
                )
                return WorkflowStep("run_tests", TaskStatus.NEEDS_HUMAN, result.error_code or "failed")
            mark_recovery_phase(self._task_id, self._store, TARGET_PASSED)
        elif target.get("ok") is True:
            self._store.append_event(
                self._task_id,
                "recovery_step_skipped",
                {"tool": "run_tests", "reason": "verified completed tool result"},
            )
        else:
            code = str(target.get("error_code") or "failed")
            self._store.transition(
                self._task_id,
                TaskStatus.NEEDS_HUMAN,
                f"candidate patch failed target test: {code}",
            )
            return WorkflowStep("run_tests", TaskStatus.NEEDS_HUMAN, code)

        regression = self._latest_tool_result("run_regression")
        if regression is None:
            result = self._tools.run_regression()
            if not result.ok:
                self._store.transition(
                    self._task_id,
                    TaskStatus.NEEDS_HUMAN,
                    f"candidate patch failed regression: {result.error_code}",
                )
                return WorkflowStep(
                    "run_regression", TaskStatus.NEEDS_HUMAN, result.error_code or "failed"
                )
        elif regression.get("ok") is True:
            self._store.append_event(
                self._task_id,
                "recovery_step_skipped",
                {"tool": "run_regression", "reason": "verified completed tool result"},
            )
        else:
            code = str(regression.get("error_code") or "failed")
            self._store.transition(
                self._task_id,
                TaskStatus.NEEDS_HUMAN,
                f"candidate patch failed regression: {code}",
            )
            return WorkflowStep("run_regression", TaskStatus.NEEDS_HUMAN, code)

        self._store.transition(
            self._task_id,
            TaskStatus.AWAITING_REVIEW,
            "candidate patch passed target and regression tests; human review required",
        )
        return WorkflowStep("run_regression", TaskStatus.AWAITING_REVIEW, "all tests passed")

    def _latest_tool_result(self, tool: str) -> dict[str, object] | None:
        matches = [
            event.payload
            for event in self._store.list_events(self._task_id)
            if event.event_type == "tool_finished" and event.payload.get("tool") == tool
        ]
        return matches[-1] if matches else None

    def _verify_applied_files(self, payload: dict[str, object]) -> str | None:
        summary = payload.get("summary", {})
        hashes = summary.get("file_sha256", {}) if isinstance(summary, dict) else {}
        if not isinstance(hashes, dict) or not hashes:
            return "patch checkpoint does not contain file hashes"
        workspace = Path(self._store.get_task(self._task_id).workspace).resolve()
        for relative, expected in hashes.items():
            if not isinstance(relative, str) or not is_allowed_source_path(
                relative, self._allowed_source_roots
            ):
                return "patch checkpoint contains a denied path"
            path = (workspace / relative).resolve()
            if not path.is_relative_to(workspace) or not path.is_file():
                return "patched file is unavailable during resume"
            # PatchApplier hashes the logical UTF-8 text before Windows newline
            # translation, so resume must use the same normalized representation.
            actual = hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            if actual != expected:
                return "patched workspace failed integrity verification"
        return None

    def _fail_resume(self, detail: str) -> WorkflowStep:
        self._store.transition(self._task_id, TaskStatus.NEEDS_HUMAN, detail)
        return WorkflowStep("resume", TaskStatus.NEEDS_HUMAN, detail)
