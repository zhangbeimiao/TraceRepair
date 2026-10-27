import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = "langgraph-review-offline-v0.7.0-dev2"


def _json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_dev2_freeze_preserves_scope_metrics_and_failure() -> None:
    frozen = _json(ROOT / "evaluation" / "frozen" / f"{BENCHMARK}.json")
    agent = _json(ROOT / "evaluation" / "frozen" / "agent-v0.7.0-dev2.json")
    failure = _json(
        ROOT
        / "evaluation"
        / "results"
        / BENCHMARK
        / "failures"
        / "tqdm-sizeless-bool.json"
    )

    assert frozen["release_agent_version"] == "0.7.0-dev2"
    assert frozen["summary"] == {
        "attempted_tasks": 5,
        "successes": 4,
        "failures": 1,
        "pass_at_1": 0.8,
        "human_handoffs": 1,
        "incorrect_accepted_patches": 0,
        "average_completion_tokens": 543.2,
        "total_completion_tokens": 2716,
        "p50_wall_seconds": 14.329,
        "p95_wall_seconds": 18.391,
        "wilson_95_percent": {"lower": 0.3755, "upper": 0.9638},
    }
    assert frozen["splits"]["locked"] == {
        "attempts": 0,
        "successes": 0,
        "not_run": True,
    }
    assert frozen["comparison"]["baseline_pass_at_1"] == 0.4
    assert agent["status"] == "frozen_development_evidence"
    assert agent["claim_scope"]["supports_generalisation_claim"] is False
    assert failure["semantic_review"]["changed"] is False
    assert failure["target_test"]["error_code"] == "TEST_FAILED"
    assert failure["regression_started"] is False
    assert failure["final_status"] == "needs_human"


def test_dev2_frozen_checksums_match_bytes() -> None:
    frozen_path = ROOT / "evaluation" / "frozen" / f"{BENCHMARK}.json"
    expected = frozen_path.with_suffix(".json.sha256").read_text(encoding="ascii").split()[0]
    assert hashlib.sha256(frozen_path.read_bytes()).hexdigest() == expected

    failure = _json(
        ROOT
        / "evaluation"
        / "results"
        / BENCHMARK
        / "failures"
        / "tqdm-sizeless-bool.json"
    )
    diff_path = ROOT / "evaluation" / "results" / BENCHMARK / failure["candidate"]["path"]
    assert hashlib.sha256(diff_path.read_bytes()).hexdigest() == failure["candidate"]["sha256"]
