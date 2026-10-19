import json
from pathlib import Path

from scripts.evaluate_locked_repository import write_attempt_marker, write_locked_manifest
from tracerepair.evaluation_report import RunMetrics


def test_locked_manifest_freezes_failure_without_hiding_it(tmp_path: Path) -> None:
    run = RunMetrics(
        task_id="model-agent-repo-held-out-example",
        case_id="repo-held-out-example",
        agent_version="0.4.0-dev1",
        status="needs_human",
        model_calls=3,
        completion_tokens=200,
        tool_calls=3,
        tool_failures=0,
        model_policy_rejections=0,
        deterministic_recoveries=0,
        target_test_passed=False,
        regression_passed=False,
        end_to_end_success=False,
        stop_reason="candidate patch failed target test",
    )
    path = tmp_path / "locked.json"

    write_locked_manifest(path, run)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["protocol"]["one_shot"] is True
    assert payload["protocol"]["retry_on_failure"] is False
    assert payload["protocol"]["repository_details_published"] is False
    assert "repository_task" not in payload["protocol"]
    assert "repository_commit" not in payload["protocol"]
    assert "config_sha256" not in payload["protocol"]
    assert "task_id" not in payload["run"]
    assert "case_id" not in payload["run"]
    assert payload["run"]["end_to_end_success"] is False
    assert payload["run"]["stop_reason"] == "candidate patch failed target test"


def test_attempt_marker_is_written_before_a_locked_provider_call(tmp_path: Path) -> None:
    path = tmp_path / "attempt.json"

    write_attempt_marker(
        path,
        repository_task="held-out-example",
        repository_commit="a" * 40,
        config_sha256="b" * 64,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["repository_task"] == "held-out-example"
    assert payload["repository_commit"] == "a" * 40
    assert payload["config_sha256"] == "b" * 64
    assert payload["started_at"].endswith("+00:00")
