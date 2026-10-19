import json
from pathlib import Path

from tracerepair.benchmark import StabilityDecision, write_freeze_manifest
from tracerepair.evaluation_report import RunMetrics


def test_repository_freeze_manifest_keeps_scope_metadata(tmp_path: Path) -> None:
    decision = StabilityDecision(
        case_id="repo-mini-repo-discount",
        agent_version="0.4.0-dev1",
        runs=1,
        successful_runs=1,
        success_rate=1.0,
        average_completion_tokens=175.0,
        average_tool_calls=5.0,
        stop_reasons={},
        minimum_runs=1,
        required_success_rate=0.8,
        stable=True,
    )
    run = RunMetrics(
        task_id="model-agent-repo-mini-repo-discount-example",
        case_id=decision.case_id,
        agent_version=decision.agent_version,
        status="awaiting_review",
        model_calls=3,
        completion_tokens=175,
        tool_calls=5,
        tool_failures=0,
        model_policy_rejections=0,
        deterministic_recoveries=0,
        target_test_passed=True,
        regression_passed=True,
        end_to_end_success=True,
        stop_reason="candidate patch passed target and regression tests; human review required",
    )
    path = tmp_path / "repository.json"

    write_freeze_manifest(
        path,
        decision,
        [run],
        metadata={
            "project_version": "0.6.1",
            "not_a_locked_generalization_result": True,
        },
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["metadata"]["project_version"] == "0.6.1"
    assert payload["metadata"]["not_a_locked_generalization_result"] is True
    assert payload["runs"][0]["task_id"] == run.task_id
