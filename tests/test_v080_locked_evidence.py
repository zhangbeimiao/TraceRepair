import hashlib
import json
from pathlib import Path

from scripts.verify_benchmark_evidence import verify_evidence


ROOT = Path(__file__).resolve().parents[1]


def test_locked_evidence_and_all_run_logs_verify() -> None:
    benchmark = "function-rag-locked-v0.8.0"
    verified = verify_evidence(ROOT, benchmark_id=benchmark)
    assert (verified["tasks"], verified["successes"], verified["ledger_records"]) == (3, 2, 6)
    report = json.loads((ROOT / "evaluation/results" / benchmark / "report.json").read_text())
    assert len({item["benchmark_task_id"] for item in report["attempts"]}) == 3
    for attempt in report["attempts"]:
        log = ROOT / attempt["log_path"]
        assert hashlib.sha256(log.read_bytes()).hexdigest() == attempt["log_sha256"]
    failure = next(item for item in report["attempts"] if not item["success"])
    assert failure["benchmark_task_id"] == "structlog-missing-event"
    assert failure["status"] == "needs_human"
    assert "ends before ConsoleRenderer.__call__" in failure["stop_reason"]
