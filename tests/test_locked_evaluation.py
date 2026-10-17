from pathlib import Path

import pytest

from tracerepair.evaluation_report import RunMetrics
from tracerepair.locked_evaluation import (
    summarize_locked_evaluation,
    write_locked_evaluation_manifest,
)


def run(case_id: str, *, success: bool = True, status: str | None = None) -> RunMetrics:
    return RunMetrics(
        task_id=f"model-agent-{case_id}",
        case_id=case_id,
        agent_version="0.4.0-dev1",
        status=status or ("awaiting_review" if success else "needs_human"),
        model_calls=3,
        completion_tokens=200,
        tool_calls=5 if success else 2,
        tool_failures=0,
        model_policy_rejections=0,
        deterministic_recoveries=0,
        target_test_passed=success,
        regression_passed=success,
        end_to_end_success=success,
        stop_reason="verified" if success else "safe stop",
    )


def test_locked_summary_freezes_successes_and_failures_once(tmp_path: Path) -> None:
    cases = ("02", "04", "06", "08", "09")
    runs = [run(case_id, success=case_id != "08") for case_id in cases]
    summary = summarize_locked_evaluation(
        runs,
        case_ids=cases,
        agent_version="0.4.0-dev1",
    )

    assert summary.complete is True
    assert summary.success_rate == 0.8
    manifest = tmp_path / "testset.json"
    write_locked_evaluation_manifest(manifest, summary, runs)
    assert manifest.is_file()


def test_locked_summary_rejects_missing_duplicate_or_running_cases(tmp_path: Path) -> None:
    cases = ("02", "04", "06", "08", "09")
    runs = [run(case_id) for case_id in cases[:-1]]
    runs.append(run("08"))
    summary = summarize_locked_evaluation(
        runs,
        case_ids=cases,
        agent_version="0.4.0-dev1",
    )
    assert summary.complete is False
    with pytest.raises(ValueError, match="incomplete or duplicated"):
        write_locked_evaluation_manifest(tmp_path / "testset.json", summary, runs)

    running = [run(case_id, status="running") if case_id == "09" else run(case_id) for case_id in cases]
    assert not summarize_locked_evaluation(
        running,
        case_ids=cases,
        agent_version="0.4.0-dev1",
    ).complete
