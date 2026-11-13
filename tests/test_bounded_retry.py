from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from evaluation.materialize import materialize_case
from tracerepair.bounded_retry import (
    BoundedRetryWorkflow,
    NativeFunctionRetryProvider,
    RetryCandidate,
    RetryInjectedCrash,
    retry_metrics,
)
from tracerepair.function_calling import NativeFunctionPlanner
from tracerepair.model_planner import PlannerConfig
from tracerepair.models import Task, TaskStatus
from tracerepair.store import TraceStore
from tests.test_repair_workflow import FIX_CASE_05, NON_FIXING_CASE_05


TARGET = "tests/test_repair_targets.py::test_case_05_parses_false_as_false"


class ScriptedProvider:
    def __init__(self, candidates: list[RetryCandidate]) -> None:
        self._candidates = candidates
        self.calls: list[tuple[int, dict[str, object] | None]] = []

    def __call__(self, attempt_id: int, feedback: dict[str, object] | None) -> RetryCandidate:
        self.calls.append((attempt_id, feedback))
        return self._candidates[attempt_id - 1]


class NativePatchTransport:
    def __init__(self, diff: str) -> None:
        self._diff = diff
        self.payloads: list[dict[str, object]] = []

    def complete(self, payload: dict[str, object]) -> dict[str, object]:
        self.payloads.append(payload)
        return {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "retry-call",
                                "type": "function",
                                "function": {
                                    "name": "propose_patch",
                                    "arguments": json.dumps(
                                        {"unified_diff": self._diff, "reason": "minimal correction"}
                                    ),
                                },
                            }
                        ]
                    }
                }
            ],
            "usage": {"completion_tokens": 17},
        }


def make_workflow(
    tmp_path: Path,
    provider: Callable[[int, dict[str, object] | None], RetryCandidate],
    *,
    crash_after_attempt: int | None = None,
) -> tuple[TraceStore, BoundedRetryWorkflow, Path]:
    baseline = materialize_case("05", tmp_path / "baseline")
    store = TraceStore(tmp_path / "data" / "trace.sqlite3")
    store.create_task(Task("bounded-retry-05", "05", "parse false", str(baseline)))
    store.transition("bounded-retry-05", TaskStatus.READY, "diagnosis complete")
    workflow = BoundedRetryWorkflow(
        "bounded-retry-05",
        store,
        baseline_workspace=baseline,
        attempts_root=tmp_path / "attempts",
        target_selector=TARGET,
        candidate_provider=provider,
        crash_after_attempt=crash_after_attempt,
    )
    return store, workflow, baseline


def test_first_failed_candidate_is_discarded_and_second_clean_attempt_can_succeed(tmp_path: Path) -> None:
    provider = ScriptedProvider(
        [
            RetryCandidate(NON_FIXING_CASE_05, model_calls=1, completion_tokens=21),
            RetryCandidate(FIX_CASE_05, model_calls=1, completion_tokens=34),
        ]
    )
    store, workflow, baseline = make_workflow(tmp_path, provider)

    result = workflow.run()

    assert result.status is TaskStatus.AWAITING_REVIEW
    assert result.attempt_count == 2
    assert result.rescued_on_second_attempt is True
    state = store.load_checkpoint("bounded-retry-05")["bounded_retry"]
    first, second = state["attempts"]
    assert first["outcome"] == "target_failed_retriable"
    assert second["outcome"] == "verified"
    assert first["workspace_before_sha256"] == second["workspace_before_sha256"]
    assert first["workspace_before_sha256"] == state["baseline_sha256"]
    assert provider.calls[1][0] == 2
    feedback = provider.calls[1][1]
    assert feedback is not None
    assert feedback["attempt_id"] == 1
    assert feedback["exit_code"] == 1
    assert len(str(feedback["output_tail"])) <= 2_000

    first_config = (tmp_path / "attempts" / "attempt-01" / "src/eventrelay/config.py").read_text()
    second_config = (tmp_path / "attempts" / "attempt-02" / "src/eventrelay/config.py").read_text()
    baseline_config = (baseline / "src/eventrelay/config.py").read_text()
    assert "Candidate accepted by policy" in first_config
    assert "Candidate accepted by policy" not in second_config
    assert "if value:" not in second_config
    assert "if value:" in baseline_config
    metrics = retry_metrics(state)
    assert metrics["success_at_1"] is False
    assert metrics["success_at_lte_2"] is True
    assert metrics["second_attempt_rescues"] == 1
    assert metrics["incorrect_patches_accepted"] == 0
    assert metrics["average_model_calls"] == 1.0
    store.close()


def test_policy_rejection_never_starts_tests_or_a_second_attempt(tmp_path: Path) -> None:
    unsafe = FIX_CASE_05.replace("src/eventrelay/config.py", "tests/test_config.py")
    provider = ScriptedProvider([RetryCandidate(unsafe)])
    store, workflow, _ = make_workflow(tmp_path, provider)

    result = workflow.run()

    assert result.status is TaskStatus.NEEDS_HUMAN
    assert result.attempt_count == 1
    state = store.load_checkpoint("bounded-retry-05")["bounded_retry"]
    assert state["attempts"][0]["outcome"] == "policy_or_patch_rejected"
    tool_names = [event.payload["tool"] for event in store.list_events("bounded-retry-05") if event.event_type == "tool_started"]
    assert tool_names == ["apply_patch"]
    assert len(provider.calls) == 1
    store.close()


def test_regression_failure_is_not_retried(tmp_path: Path) -> None:
    provider = ScriptedProvider([RetryCandidate(FIX_CASE_05), RetryCandidate(FIX_CASE_05)])
    store, workflow, baseline = make_workflow(tmp_path, provider)
    retry_module = baseline / "src/eventrelay/retry.py"
    retry_module.write_text(
        retry_module.read_text(encoding="utf-8").replace(
            "return status_code == 429 or status_code >= 500", "return status_code >= 500"
        ),
        encoding="utf-8",
    )

    result = workflow.run()

    assert result.status is TaskStatus.NEEDS_HUMAN
    assert result.attempt_count == 1
    state = store.load_checkpoint("bounded-retry-05")["bounded_retry"]
    assert state["attempts"][0]["outcome"] == "regression_failed"
    assert len(provider.calls) == 1
    store.close()


def test_resume_uses_next_attempt_and_never_repeats_durable_failed_candidate(tmp_path: Path) -> None:
    first_provider = ScriptedProvider([RetryCandidate(NON_FIXING_CASE_05)])
    store, crashing_workflow, baseline = make_workflow(
        tmp_path, first_provider, crash_after_attempt=1
    )

    with pytest.raises(RetryInjectedCrash):
        crashing_workflow.run()

    state_after_crash = store.load_checkpoint("bounded-retry-05")["bounded_retry"]
    assert len(state_after_crash["attempts"]) == 1
    assert store.get_task("bounded-retry-05").status is TaskStatus.INTERRUPTED
    first_config = (tmp_path / "attempts" / "attempt-01" / "src/eventrelay/config.py").read_text()

    store.transition("bounded-retry-05", TaskStatus.READY, "restart after process crash")
    resumed_provider = ScriptedProvider([RetryCandidate(FIX_CASE_05)])
    resumed = BoundedRetryWorkflow(
        "bounded-retry-05",
        store,
        baseline_workspace=baseline,
        attempts_root=tmp_path / "attempts",
        target_selector=TARGET,
        candidate_provider=lambda attempt_id, feedback: resumed_provider(1, feedback),
    )
    result = resumed.run()

    assert result.status is TaskStatus.AWAITING_REVIEW
    assert [item["attempt_id"] for item in store.load_checkpoint("bounded-retry-05")["bounded_retry"]["attempts"]] == [1, 2]
    assert len(first_provider.calls) == 1
    assert len(resumed_provider.calls) == 1
    assert (tmp_path / "attempts" / "attempt-01" / "src/eventrelay/config.py").read_text() == first_config
    store.close()


def test_native_retry_provider_advertises_only_patch_and_handoff(tmp_path: Path) -> None:
    store, _, _ = make_workflow(tmp_path, ScriptedProvider([RetryCandidate(FIX_CASE_05)]))
    transport = NativePatchTransport(FIX_CASE_05)
    provider = NativeFunctionRetryProvider(
        NativeFunctionPlanner(
            transport,
            PlannerConfig(
                max_completion_tokens=100,
                max_calls_per_task=2,
                max_total_completion_tokens=200,
            ),
        ),
        "bounded-retry-05",
        store,
        "src/eventrelay/config.py: confirmed source slice",
    )

    candidate = provider(
        2,
        {
            "attempt_id": 1,
            "exit_code": 1,
            "error_code": "TEST_FAILED",
            "output_tail": "AssertionError: false was true",
        },
    )

    assert candidate.unified_diff == FIX_CASE_05.rstrip("\n")
    assert candidate.model_calls == 1
    assert candidate.completion_tokens == 17
    advertised = [item["function"]["name"] for item in transport.payloads[0]["tools"]]
    assert advertised == ["propose_patch", "handoff"]
    messages = transport.payloads[0]["messages"]
    assert "AssertionError: false was true" not in messages[0]["content"]
    assert "AssertionError: false was true" in messages[1]["content"]
    model_event = [event for event in store.list_events("bounded-retry-05") if event.event_type == "model_plan_recorded"][-1]
    assert model_event.payload["stage"] == "retry_patch"
    assert model_event.payload["prompt_id"] == "retry-patch-native-tools-v0.9.0-dev1"
    store.close()
