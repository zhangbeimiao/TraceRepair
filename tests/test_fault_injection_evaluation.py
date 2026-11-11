import json

import pytest

from evaluation.fault_injection import default_output_path, load_suite, render_markdown


def test_recovery_suite_has_unique_safe_scenarios() -> None:
    suite = load_suite("recovery_v1")
    identifiers = [item["id"] for item in suite["scenarios"]]
    assert len(identifiers) == len(set(identifiers)) == 10
    assert all(item["selector"].startswith("tests/") for item in suite["scenarios"])
    assert all(item["invariants"] for item in suite["scenarios"])


def test_unknown_suite_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown"):
        load_suite("does-not-exist")


def test_default_replay_directory_is_ignored_runs_directory() -> None:
    output = default_output_path("recovery_v1")
    assert output.parent.name == "runs"
    assert output.name == "fault-recovery_v1.json"


def test_markdown_keeps_failure_and_claim_boundary() -> None:
    report = {
        "suite_id": "example",
        "description": "Example evidence.",
        "execution": {"provider_requests": 0},
        "summary": {
            "scenarios": 1,
            "passed": 0,
            "failed": 1,
            "total_duration_seconds": 0.1,
        },
        "results": [
            {
                "id": "failure",
                "category": "integrity_conflict",
                "passed": False,
                "duration_seconds": 0.1,
                "invariants": ["tests never start"],
            }
        ],
        "claim_boundary": "Bounded evidence only.",
    }
    markdown = render_markdown(json.loads(json.dumps(report)))
    assert "FAIL" in markdown
    assert "tests never start" in markdown
    assert "Bounded evidence only" in markdown
