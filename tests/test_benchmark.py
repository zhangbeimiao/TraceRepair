import json
from pathlib import Path

import pytest

from tracerepair.benchmark import (
    assess_stability,
    assess_suite_stability,
    write_freeze_manifest,
    write_suite_freeze_manifest,
)
from tracerepair.evaluation_report import TraceEvaluator
from tracerepair.models import Task, TaskStatus
from tracerepair.store import TraceStore


def make_cohort(tmp_path: Path, successes: int) -> Path:
    database = tmp_path / "cohort.sqlite3"
    store = TraceStore(database)
    for index in range(5):
        task_id = f"model-agent-{index}"
        store.create_task(Task(task_id, "05", "issue", f"D:/{index}"))
        store.append_event(task_id, "run_metadata", {"agent_version": "0.3.0"})
        store.transition(task_id, TaskStatus.READY, "ready")
        store.transition(task_id, TaskStatus.RUNNING, "run")
        store.append_event(
            task_id,
            "model_plan_recorded",
            {"completion_tokens": 100 + index, "policy_accepted": True},
        )
        if index < successes:
            for tool in ("run_tests", "run_regression"):
                store.append_event(
                    task_id,
                    "tool_finished",
                    {"call_id": f"{index}-{tool}", "tool": tool, "ok": True},
                )
            store.transition(task_id, TaskStatus.AWAITING_REVIEW, "verified")
        else:
            store.transition(task_id, TaskStatus.NEEDS_HUMAN, "safe stop")
    store.close()
    return database


def test_four_of_five_runs_meets_stability_threshold_and_can_freeze(tmp_path: Path) -> None:
    evaluator = TraceEvaluator(make_cohort(tmp_path, successes=4))
    decision = assess_stability(evaluator, case_id="05", agent_version="0.3.0")

    assert decision.stable is True
    assert decision.success_rate == 0.8
    manifest = tmp_path / "frozen.json"
    write_freeze_manifest(manifest, decision, evaluator.runs(agent_version="0.3.0"))
    saved = json.loads(manifest.read_text(encoding="utf-8"))
    assert saved["decision"]["stable"] is True
    assert len(saved["runs"]) == 5
    evaluator.close()


def test_three_of_five_runs_does_not_freeze(tmp_path: Path) -> None:
    evaluator = TraceEvaluator(make_cohort(tmp_path, successes=3))
    decision = assess_stability(evaluator, case_id="05", agent_version="0.3.0")

    assert decision.stable is False
    with pytest.raises(ValueError, match="unstable"):
        write_freeze_manifest(tmp_path / "frozen.json", decision, evaluator.runs())
    evaluator.close()


def make_suite_cohort(tmp_path: Path, failed_case: str | None = None) -> Path:
    database = tmp_path / "suite.sqlite3"
    store = TraceStore(database)
    for case_id in ("01", "03", "07", "10"):
        for index in range(2):
            task_id = f"model-agent-{case_id}-{index}"
            store.create_task(Task(task_id, case_id, "issue", f"D:/{case_id}/{index}"))
            store.append_event(task_id, "run_metadata", {"agent_version": "0.4.0-dev1"})
            store.transition(task_id, TaskStatus.READY, "ready")
            store.transition(task_id, TaskStatus.RUNNING, "run")
            store.append_event(
                task_id,
                "model_plan_recorded",
                {"completion_tokens": 200, "policy_accepted": True},
            )
            if case_id != failed_case:
                for tool in ("run_tests", "run_regression"):
                    store.append_event(
                        task_id,
                        "tool_finished",
                        {"call_id": f"{task_id}-{tool}", "tool": tool, "ok": True},
                    )
                store.transition(task_id, TaskStatus.AWAITING_REVIEW, "verified")
            else:
                store.transition(task_id, TaskStatus.NEEDS_HUMAN, "safe stop")
    store.close()
    return database


def test_development_suite_can_freeze_after_two_successes_per_case(tmp_path: Path) -> None:
    evaluator = TraceEvaluator(make_suite_cohort(tmp_path))
    decision = assess_suite_stability(
        evaluator,
        case_ids=("01", "03", "07", "10"),
        agent_version="0.4.0-dev1",
    )

    assert decision.stable is True
    assert decision.runs == 8
    assert decision.success_rate == 1.0
    manifest = tmp_path / "devset.json"
    write_suite_freeze_manifest(
        manifest,
        decision,
        evaluator.runs(agent_version="0.4.0-dev1"),
    )
    saved = json.loads(manifest.read_text(encoding="utf-8"))
    assert saved["decision"]["case_ids"] == ["01", "03", "07", "10"]
    assert len(saved["runs"]) == 8
    evaluator.close()


def test_development_suite_rejects_a_case_with_no_successes(tmp_path: Path) -> None:
    evaluator = TraceEvaluator(make_suite_cohort(tmp_path, failed_case="10"))
    decision = assess_suite_stability(
        evaluator,
        case_ids=("01", "03", "07", "10"),
        agent_version="0.4.0-dev1",
    )

    assert decision.success_rate == 0.75
    assert decision.stable is False
    with pytest.raises(ValueError, match="unstable suite"):
        write_suite_freeze_manifest(tmp_path / "devset.json", decision, evaluator.runs())
    evaluator.close()
