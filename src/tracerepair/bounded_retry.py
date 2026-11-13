"""Bounded, clean-snapshot candidate retry runtime.

This module deliberately sits beside the one-shot LangGraph workflow.  It is a
development runtime for ``0.9.0-dev1``: it accepts candidate diffs from a
planner adapter, but keeps retry eligibility, workspaces, test gates, and
durable attempt records deterministic.

The important invariant is that a failed candidate is never the input to the
next candidate.  Every attempt receives a newly materialised copy of the same
baseline snapshot.
"""

from __future__ import annotations

import hashlib
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tracerepair.function_calling import NativeFunctionPlanner
from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.model_planner import BudgetExceeded, PlannerError
from tracerepair.models import TaskStatus
from tracerepair.patch_apply import PatchApplier
from tracerepair.read_tools import ReadOnlyRepository
from tracerepair.store import TraceStore
from tracerepair.test_runner import RestrictedTestRunner, TestRunResult


RETRY_AGENT_VERSION = "0.9.0-dev1"
_CHECKPOINT_KEY = "bounded_retry"
_IGNORED_DIRECTORIES = {".git", ".pytest_cache", ".tmp", ".tracerepair", "__pycache__"}
_SYNTAX_MARKERS = ("SyntaxError", "IndentationError", "TabError")


class RetryInjectedCrash(RuntimeError):
    """Test-only fault used to prove completed attempts are not repeated."""


class RetryProviderError(RuntimeError):
    """A model-side refusal or invalid response that cannot be retried automatically."""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 2
    timeout_seconds: int = 30
    max_feedback_characters: int = 2_000

    def __post_init__(self) -> None:
        if self.max_attempts != 2:
            raise ValueError("0.9.0-dev1 permits exactly two candidate attempts")
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be at least 1")
        if not 200 <= self.max_feedback_characters <= 8_000:
            raise ValueError("max_feedback_characters must be between 200 and 8000")


@dataclass(frozen=True)
class RetryCandidate:
    unified_diff: str
    model_calls: int = 0
    completion_tokens: int = 0
    planner_reason: str = ""


@dataclass(frozen=True)
class RetryResult:
    status: TaskStatus
    attempt_count: int
    rescued_on_second_attempt: bool
    stop_reason: str


CandidateProvider = Callable[[int, dict[str, Any] | None], RetryCandidate]


class NativeFunctionRetryProvider:
    """Adapter that gives the model proposal authority, never execution authority.

    Source evidence is pre-confirmed by the diagnosis graph.  This adapter
    advertises only ``propose_patch`` and ``handoff``.  It has no repository,
    shell, test, or patch-application access.
    """

    def __init__(
        self,
        planner: NativeFunctionPlanner,
        task_id: str,
        store: TraceStore,
        source_evidence: str,
    ) -> None:
        if not source_evidence.strip():
            raise ValueError("source_evidence must not be empty")
        self._planner = planner
        self._task_id = task_id
        self._store = store
        self._source_evidence = source_evidence

    def __call__(self, attempt_id: int, feedback: dict[str, Any] | None) -> RetryCandidate:
        evidence = {
            "attempt_id": attempt_id,
            "maximum_attempts": 2,
            "confirmed_source_evidence": self._source_evidence,
            "prior_target_failure": feedback,
        }
        try:
            plan = self._planner.suggest(
                self._task_id,
                self._store,
                _canonical_evidence(evidence),
                allowed_tools=set(),
                allow_patch=True,
                stage="retry_patch",
            )
        except (BudgetExceeded, PlannerError) as error:
            raise RetryProviderError(str(error)) from error
        if plan.kind == "handoff":
            raise RetryProviderError(f"model requested handoff: {plan.reason}")
        if plan.kind != "patch" or not plan.unified_diff:
            raise RetryProviderError("model did not return a patch proposal")
        return RetryCandidate(
            unified_diff=plan.unified_diff,
            model_calls=1,
            completion_tokens=plan.completion_tokens,
            planner_reason=plan.reason,
        )


class BoundedRetryWorkflow:
    """Verify at most two model candidates, each in a clean disposable copy.

    The provider is intentionally a narrow callable.  It can later be backed by
    the native Function Calling planner, while this class remains responsible
    for every side effect and every retry decision.
    """

    def __init__(
        self,
        task_id: str,
        store: TraceStore,
        *,
        baseline_workspace: Path,
        attempts_root: Path,
        target_selector: str,
        candidate_provider: CandidateProvider,
        allowed_source_roots: tuple[str, ...] = ("src/eventrelay",),
        regression_selector: str = "tests",
        pythonpath: tuple[str, ...] = ("src",),
        policy: RetryPolicy | None = None,
        crash_after_attempt: int | None = None,
    ) -> None:
        baseline = baseline_workspace.resolve()
        if not baseline.is_dir():
            raise ValueError(f"baseline workspace does not exist: {baseline_workspace}")
        if not target_selector:
            raise ValueError("target_selector is required")
        self._task_id = task_id
        self._store = store
        self._baseline = baseline
        self._attempts_root = attempts_root.resolve()
        self._target_selector = target_selector
        self._candidate_provider = candidate_provider
        self._allowed_source_roots = allowed_source_roots
        self._regression_selector = regression_selector
        self._pythonpath = pythonpath
        self._policy = policy or RetryPolicy()
        self._crash_after_attempt = crash_after_attempt

    def run(self) -> RetryResult:
        """Run or resume safely; previously recorded attempts are never replayed."""

        self._ensure_running()
        checkpoint = self._checkpoint()
        retry_state = checkpoint.get(_CHECKPOINT_KEY)
        if retry_state is None:
            retry_state = self._new_retry_state()
            checkpoint[_CHECKPOINT_KEY] = retry_state
            self._store.save_checkpoint(self._task_id, checkpoint)
            self._store.append_event(
                self._task_id,
                "retry_initialized",
                {"agent_version": RETRY_AGENT_VERSION, "baseline_sha256": retry_state["baseline_sha256"]},
            )
        self._validate_retry_state(retry_state)

        active = retry_state.get("active_attempt")
        if active is not None:
            return self._stop(
                retry_state,
                "interrupted attempt has no durable completion record; fail closed",
            )

        attempts = list(retry_state["attempts"])
        if attempts and attempts[-1]["outcome"] == "target_failed_retriable":
            if len(attempts) >= self._policy.max_attempts:
                return self._stop(retry_state, "candidate retry budget exhausted")
            feedback = attempts[-1]["failure_feedback"]
        elif attempts:
            return self._terminal_from_record(retry_state, attempts[-1])
        else:
            feedback = None

        attempt_id = len(attempts) + 1
        return self._execute_attempt(retry_state, attempt_id, feedback)

    def _execute_attempt(
        self,
        retry_state: dict[str, Any],
        attempt_id: int,
        feedback: dict[str, Any] | None,
    ) -> RetryResult:
        workspace, before_hash = self._materialize_attempt(attempt_id, retry_state["baseline_sha256"])
        retry_state["active_attempt"] = attempt_id
        self._save_retry_state(retry_state)
        self._store.append_event(
            self._task_id,
            "retry_attempt_started",
            {
                "attempt_id": attempt_id,
                "source_snapshot_sha256": before_hash,
                "has_failure_feedback": feedback is not None,
            },
        )

        started = time.monotonic()
        try:
            candidate = self._candidate_provider(attempt_id, feedback)
        except Exception as error:  # provider errors must never leave an active attempt resumable
            return self._record_and_stop(
                retry_state,
                self._attempt_record(
                    attempt_id, workspace, before_hash, started,
                    outcome="candidate_generation_error",
                    stop_reason=f"candidate provider failed: {type(error).__name__}",
                ),
            )
        if not isinstance(candidate, RetryCandidate):
            return self._record_and_stop(
                retry_state,
                self._attempt_record(
                    attempt_id, workspace, before_hash, started,
                    outcome="candidate_generation_error",
                    stop_reason="candidate provider returned an invalid candidate",
                ),
            )

        diff_hash = _sha256_text(candidate.unified_diff)
        tools = self._tools_for(workspace)
        applied = tools.apply_patch(candidate.unified_diff)
        base = self._attempt_record(
            attempt_id,
            workspace,
            before_hash,
            started,
            candidate=candidate,
            diff_sha256=diff_hash,
            applied=applied,
        )
        if not applied.ok:
            base.update(
                outcome="policy_or_patch_rejected",
                stop_reason=f"candidate patch rejected: {applied.error_code or 'unknown'}",
            )
            self._complete_record(base, workspace, started)
            return self._record_and_stop(retry_state, base)

        target = tools.run_tests(self._target_selector)
        base["target"] = _test_summary(target)
        if not target.ok:
            feedback_payload = self._failure_feedback(target, attempt_id, diff_hash)
            if self._can_retry_target(target) and attempt_id < self._policy.max_attempts:
                base.update(
                    outcome="target_failed_retriable",
                    stop_reason="target test failed; one clean-snapshot retry is permitted",
                    failure_feedback=feedback_payload,
                )
                self._complete_record(base, workspace, started)
                return self._record_retriable_failure(retry_state, base)
            base.update(
                outcome="target_failed_final",
                stop_reason=self._target_stop_reason(target, attempt_id),
                failure_feedback=feedback_payload,
            )
            self._complete_record(base, workspace, started)
            return self._record_and_stop(retry_state, base)

        regression = tools.run_regression()
        base["regression"] = _test_summary(regression)
        if not regression.ok:
            base.update(
                outcome="regression_failed",
                stop_reason="regression test failed; automatic retry is not permitted",
            )
            self._complete_record(base, workspace, started)
            return self._record_and_stop(retry_state, base)

        base.update(outcome="verified", stop_reason="candidate passed target and regression tests")
        self._complete_record(base, workspace, started)
        retry_state["active_attempt"] = None
        retry_state["attempts"].append(base)
        self._save_retry_state(retry_state)
        self._store.append_event(
            self._task_id,
            "retry_attempt_verified",
            {"attempt_id": attempt_id, "rescued": attempt_id == 2},
        )
        self._store.transition(
            self._task_id,
            TaskStatus.AWAITING_REVIEW,
            "bounded retry candidate passed deterministic target and regression gates",
        )
        return RetryResult(TaskStatus.AWAITING_REVIEW, attempt_id, attempt_id == 2, base["stop_reason"])

    def _record_retriable_failure(self, retry_state: dict[str, Any], record: dict[str, Any]) -> RetryResult:
        retry_state["active_attempt"] = None
        retry_state["attempts"].append(record)
        self._save_retry_state(retry_state)
        self._store.append_event(
            self._task_id,
            "retry_attempt_failed",
            {"attempt_id": record["attempt_id"], "retry_eligible": True, "outcome": record["outcome"]},
        )
        if self._crash_after_attempt == record["attempt_id"]:
            self._store.transition(self._task_id, TaskStatus.INTERRUPTED, "injected crash after durable failed attempt")
            raise RetryInjectedCrash(f"injected crash after attempt {record['attempt_id']}")
        return self.run()

    def _record_and_stop(self, retry_state: dict[str, Any], record: dict[str, Any]) -> RetryResult:
        retry_state["active_attempt"] = None
        retry_state["attempts"].append(record)
        self._save_retry_state(retry_state)
        self._store.append_event(
            self._task_id,
            "retry_attempt_failed",
            {"attempt_id": record["attempt_id"], "retry_eligible": False, "outcome": record["outcome"]},
        )
        return self._stop(retry_state, record["stop_reason"])

    def _stop(self, retry_state: dict[str, Any], reason: str) -> RetryResult:
        task = self._store.get_task(self._task_id)
        if task.status is TaskStatus.RUNNING:
            self._store.transition(self._task_id, TaskStatus.NEEDS_HUMAN, reason)
        return RetryResult(TaskStatus.NEEDS_HUMAN, len(retry_state["attempts"]), False, reason)

    def _terminal_from_record(self, retry_state: dict[str, Any], record: dict[str, Any]) -> RetryResult:
        status = self._store.get_task(self._task_id).status
        rescued = record["outcome"] == "verified" and record["attempt_id"] == 2
        return RetryResult(status, len(retry_state["attempts"]), rescued, record["stop_reason"])

    def _ensure_running(self) -> None:
        task = self._store.get_task(self._task_id)
        if task.status is TaskStatus.READY:
            self._store.transition(self._task_id, TaskStatus.RUNNING, "bounded retry workflow started")
        elif task.status is not TaskStatus.RUNNING:
            raise ValueError(f"task is not runnable: {task.status}")

    def _new_retry_state(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "agent_version": RETRY_AGENT_VERSION,
            "baseline_sha256": _tree_sha256(self._baseline),
            "max_attempts": self._policy.max_attempts,
            "attempts": [],
            "active_attempt": None,
        }

    def _checkpoint(self) -> dict[str, Any]:
        return self._store.load_checkpoint(self._task_id)

    def _save_retry_state(self, retry_state: dict[str, Any]) -> None:
        checkpoint = self._checkpoint()
        checkpoint[_CHECKPOINT_KEY] = retry_state
        self._store.save_checkpoint(self._task_id, checkpoint)

    def _validate_retry_state(self, state: dict[str, Any]) -> None:
        if state.get("schema_version") != 1 or state.get("agent_version") != RETRY_AGENT_VERSION:
            raise ValueError("retry checkpoint schema or agent version does not match")
        if state.get("baseline_sha256") != _tree_sha256(self._baseline):
            raise ValueError("baseline workspace hash changed; refusing to continue retry task")
        if state.get("max_attempts") != self._policy.max_attempts:
            raise ValueError("retry policy does not match durable checkpoint")
        attempts = state.get("attempts")
        if not isinstance(attempts, list) or len(attempts) > self._policy.max_attempts:
            raise ValueError("retry checkpoint attempts are invalid")

    def _materialize_attempt(self, attempt_id: int, expected_hash: str) -> tuple[Path, str]:
        self._attempts_root.mkdir(parents=True, exist_ok=True)
        workspace = self._attempts_root / f"attempt-{attempt_id:02d}"
        if workspace.exists():
            raise ValueError(f"attempt workspace already exists: {workspace.name}")
        shutil.copytree(self._baseline, workspace, ignore=_copy_ignore)
        snapshot_hash = _tree_sha256(workspace)
        if snapshot_hash != expected_hash:
            raise ValueError("materialized attempt does not match the clean baseline snapshot")
        return workspace, snapshot_hash

    def _tools_for(self, workspace: Path) -> InstrumentedTools:
        runner = RestrictedTestRunner(
            workspace,
            allowed_targets=(self._target_selector,),
            regression_selector=self._regression_selector,
            pythonpath=self._pythonpath,
            timeout_seconds=self._policy.timeout_seconds,
        )
        return InstrumentedTools(
            self._task_id,
            self._store,
            ReadOnlyRepository(workspace, allowed_roots=self._allowed_source_roots),
            runner,
            PatchApplier(workspace),
        )

    def _attempt_record(
        self,
        attempt_id: int,
        workspace: Path,
        before_hash: str,
        started: float,
        *,
        candidate: RetryCandidate | None = None,
        diff_sha256: str | None = None,
        applied: Any | None = None,
        outcome: str = "",
        stop_reason: str = "",
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "attempt_id": attempt_id,
            "workspace": workspace.name,
            "source_snapshot_sha256": before_hash,
            "workspace_before_sha256": before_hash,
            "workspace_after_sha256": _tree_sha256(workspace),
            "elapsed_ms": int((time.monotonic() - started) * 1_000),
            "outcome": outcome,
            "stop_reason": stop_reason,
        }
        if candidate is not None:
            record.update(
                diff_sha256=diff_sha256,
                model_calls=candidate.model_calls,
                completion_tokens=candidate.completion_tokens,
                planner_reason=candidate.planner_reason,
            )
        if applied is not None:
            record["patch"] = {
                "ok": applied.ok,
                "error_code": applied.error_code,
                "files": list(applied.files),
                "file_sha256": applied.file_sha256,
            }
            record["workspace_after_sha256"] = _tree_sha256(workspace)
        return record

    @staticmethod
    def _complete_record(record: dict[str, Any], workspace: Path, started: float) -> None:
        """Capture final duration and content hash after all candidate-side effects."""

        record["elapsed_ms"] = int((time.monotonic() - started) * 1_000)
        record["workspace_after_sha256"] = _tree_sha256(workspace)

    def _failure_feedback(self, result: TestRunResult, attempt_id: int, diff_hash: str) -> dict[str, Any]:
        text = (result.stdout + "\n" + result.stderr).strip()
        text = text[-self._policy.max_feedback_characters :]
        return {
            "attempt_id": attempt_id,
            "candidate_diff_sha256": diff_hash,
            "selector": result.selector,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "error_code": result.error_code,
            "output_truncated": result.output_truncated,
            "output_tail": text,
        }

    @staticmethod
    def _can_retry_target(result: TestRunResult) -> bool:
        if result.timed_out or result.error_code != "TEST_FAILED" or result.exit_code != 1:
            return False
        combined = result.stdout + "\n" + result.stderr
        return True if "AssertionError" in combined or "FAILED" in combined else any(
            marker in combined for marker in _SYNTAX_MARKERS
        )

    @staticmethod
    def _target_stop_reason(result: TestRunResult, attempt_id: int) -> str:
        if result.timed_out:
            return "target test timed out; automatic retry is not permitted"
        if attempt_id >= 2:
            return "second candidate failed target test; retry budget exhausted"
        return "target failure is not a safe retry category"


def _test_summary(result: TestRunResult) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "selector": result.selector,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "duration_ms": result.duration_ms,
        "error_code": result.error_code,
        "output_truncated": result.output_truncated,
        "stdout_sha256": _sha256_text(result.stdout),
        "stderr_sha256": _sha256_text(result.stderr),
    }


def _copy_ignore(directory: str, names: list[str]) -> set[str]:
    del directory
    return {name for name in names if name in _IGNORED_DIRECTORIES}


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root)
        if any(part in _IGNORED_DIRECTORIES for part in relative.parts):
            continue
        if path.is_dir():
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_evidence(value: dict[str, Any]) -> str:
    """Keep the retry prompt structured while still treating it as untrusted evidence."""

    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def retry_metrics(retry_state: dict[str, Any]) -> dict[str, Any]:
    """Return transparent run metrics without treating review as auto-acceptance.

    This shape is intentionally suitable for a future development/locked
    evaluator.  ``incorrect_patches_accepted`` is always zero for this runtime:
    deterministic success only reaches ``awaiting_review`` and cannot merge.
    """

    attempts = list(retry_state.get("attempts", []))
    verified = [item for item in attempts if item.get("outcome") == "verified"]
    first_success = bool(verified and verified[0].get("attempt_id") == 1)
    rescued = bool(verified and verified[0].get("attempt_id") == 2)
    return {
        "attempts": len(attempts),
        "success_at_1": first_success,
        "success_at_lte_2": bool(verified),
        "needs_human": not bool(verified),
        "second_attempt_rescues": int(rescued),
        "incorrect_patches_accepted": 0,
        "average_completion_tokens": _average(attempts, "completion_tokens"),
        "average_model_calls": _average(attempts, "model_calls"),
        "average_attempt_elapsed_ms": _average(attempts, "elapsed_ms"),
        "stop_reasons": [str(item.get("stop_reason", "")) for item in attempts],
    }


def _average(items: list[dict[str, Any]], field: str) -> float:
    if not items:
        return 0.0
    return sum(float(item.get(field, 0)) for item in items) / len(items)
