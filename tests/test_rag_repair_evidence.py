import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "evaluation/results/rag-repair-v0.8.0-dev2.1"
FROZEN = ROOT / "evaluation/frozen/rag-repair-v0.8.0-dev2.1.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_rag_repair_development_evidence_is_frozen_and_honest() -> None:
    report = json.loads((RESULT / "report.json").read_text(encoding="utf-8"))
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    comparison = json.loads(
        (RESULT / "rag-comparison.json").read_text(encoding="utf-8")
    )

    assert report["summary"]["successes"] == 3
    assert report["summary"]["pass_at_1"] == 0.6
    assert report["summary"]["human_handoffs"] == 2
    assert report["summary"]["incorrect_accepted_patches"] == 0
    assert frozen["summary"] == {
        "attempted_tasks": 5,
        "successes": 3,
        "pass_at_1": 0.6,
        "human_handoffs": 2,
        "incorrect_accepted_patches": 0,
        "average_completion_tokens": 473.6,
        "p50_wall_seconds": 14.828,
        "p95_wall_seconds": 18.906,
    }
    assert comparison["delta"]["pass_at_1"] == 0.0
    assert comparison["candidate"]["incorrect_accepted_patches"] == 0


def test_rag_repair_hashes_and_rejected_candidate_are_verifiable() -> None:
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    integrity = frozen["integrity"]

    assert integrity["report_file_sha256"] == _sha256(RESULT / "report.json")
    assert integrity["attempts_sha256"] == _sha256(RESULT / "attempts.jsonl")
    assert integrity["manifest_lock_sha256"] == _sha256(RESULT / "manifest.lock.json")
    assert integrity["manifest_sha256"] == _sha256(
        ROOT / "evaluation/benchmarks/rag-repair-v0.8.0-dev2.1.json"
    )
    assert (FROZEN.with_suffix(".json.sha256")).read_text(encoding="utf-8").split()[0] == _sha256(FROZEN)
    assert (RESULT / "rag-comparison.json.sha256").read_text(encoding="utf-8").split()[0] == _sha256(
        RESULT / "rag-comparison.json"
    )

    failure = json.loads(
        (RESULT / "failures/httpie-host-header-offline.json").read_text(encoding="utf-8")
    )
    assert failure["error_code"] == "PATCH_PARSE_ERROR"
    assert failure["patch_applied"] is False
    assert failure["tests_started"] is False
    assert failure["candidate_sha256"] == integrity["rejected_httpie_candidate_sha256"]
    assert failure["published_diff_sha256"] == _sha256(
        RESULT / "failures/httpie-host-header-offline.diff"
    )
