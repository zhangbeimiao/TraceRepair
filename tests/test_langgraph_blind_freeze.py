import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = "langgraph-blind-v0.7.0-dev2"


def _json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_blind_result_is_frozen_as_one_shot_evidence() -> None:
    frozen_path = ROOT / "evaluation" / "frozen" / f"{BENCHMARK}.json"
    frozen = _json(frozen_path)
    checksum = frozen_path.with_suffix(".json.sha256").read_text(encoding="ascii").split()[0]

    assert _sha256(frozen_path) == checksum
    assert frozen["release_agent_version"] == "0.7.0-dev2"
    assert frozen["summary"] == {
        "attempted_tasks": 3,
        "successes": 1,
        "failures": 2,
        "pass_at_1": 0.3333,
        "human_handoffs": 2,
        "incorrect_accepted_patches": 0,
        "average_completion_tokens": 533.67,
        "total_completion_tokens": 1601,
        "p50_wall_seconds": 14.718,
        "p95_wall_seconds": 16.265,
        "wilson_95_percent": {"lower": 0.0615, "upper": 0.7923},
    }
    locked = frozen["splits"]["locked"]
    assert locked["attempts"] == 3
    assert locked["one_shot"] is True
    assert locked["retried"] is False
    assert locked["all_outcomes_published"] is True


def test_blind_report_ledger_and_failure_artifacts_match_trace_hashes() -> None:
    result = ROOT / "evaluation" / "results" / BENCHMARK
    frozen = _json(ROOT / "evaluation" / "frozen" / f"{BENCHMARK}.json")
    report_path = result / "report.json"
    report = _json(report_path)
    records = [
        json.loads(line)
        for line in (result / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert _sha256(report_path) == frozen["report_sha256"]
    assert len(records) == 6
    assert [record["record_kind"] for record in records].count("attempt_started") == 3
    assert [record["record_kind"] for record in records].count("attempt_finished") == 3
    assert records[-1]["record_sha256"] == frozen["terminal_ledger_sha256"]
    assert report["summary"]["incorrect_accepted_patches"] == 0

    pretty = _json(result / "failures" / "prettytable-horizontal-align.json")
    glom = _json(result / "failures" / "glom-path-index-boundary.json")
    assert _sha256(result / "failures" / "prettytable-horizontal-align.diff") == pretty[
        "candidate"
    ]["sha256"]
    assert pretty["target_test"]["passed"] is True
    assert pretty["regression_test"]["passed"] is False
    assert _sha256(result / "failures" / "glom-path-index-boundary.diff") == glom[
        "draft_candidate"
    ]["sha256"]
    assert glom["draft_candidate"]["applied_to_disposable_workspace"] is False
    assert glom["target_test_started"] is False
    assert glom["semantic_review"]["parse_error"] == "model reason is invalid"
