import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_agent_v060_freeze_pins_evaluated_config_before_locked_run() -> None:
    frozen = json.loads(
        (ROOT / "evaluation/frozen/agent-v0.6.0.json").read_text(encoding="utf-8")
    )
    config_path = ROOT / str(frozen["configuration"]["path"])

    assert frozen["status"] == "frozen_for_locked_evaluation"
    assert frozen["evaluated_runtime_agent_version"] == "0.6.0-dev4"
    assert frozen["benchmark"]["development_attempts"] == 3
    assert frozen["benchmark"]["development_successes"] == 2
    assert frozen["benchmark"]["incorrect_accepted_patches"] == 0
    assert frozen["locked_protocol"]["attempts_at_freeze"] == 0
    assert frozen["locked_protocol"]["maximum_attempts_per_task"] == 1
    assert hashlib.sha256(config_path.read_bytes()).hexdigest() == frozen["configuration"][
        "sha256"
    ]


def test_completed_locked_workflow_is_read_only_and_has_no_provider_credentials() -> None:
    workflow = (ROOT / ".github/workflows/historical-locked.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "verify_benchmark_evidence.py" in workflow
    assert "run_benchmark.py" not in workflow
    assert "DASHSCOPE_API_KEY" not in workflow
    assert "TRACEREPAIR_BAILIAN_BASE_URL" not in workflow
    assert "--split locked" not in workflow
    assert "--split development" not in workflow
    assert "--split all" not in workflow
    assert "39584933038" in workflow
