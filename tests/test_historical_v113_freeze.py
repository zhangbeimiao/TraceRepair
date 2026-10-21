import hashlib
import json
from pathlib import Path

from tracerepair.benchmark_suite import read_ledger


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "evaluation/results/historical-python-v1.1.3"
FROZEN = ROOT / "evaluation/frozen/historical-python-v1.1.3.json"


def test_complete_v113_report_and_ledger_match_frozen_summary() -> None:
    report = json.loads((RESULT / "report.json").read_text(encoding="utf-8"))
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    records = read_ledger(RESULT / "attempts.jsonl")

    assert len(records) == 10
    assert report["summary"]["attempted_tasks"] == 5
    assert report["summary"]["missing_task_ids"] == []
    assert report["summary"]["successes"] == frozen["summary"]["successes"] == 3
    assert report["summary"]["pass_at_1"] == frozen["summary"]["pass_at_1"] == 0.6
    assert report["summary"]["incorrect_accepted_patches"] == 0
    assert records[-1]["record_sha256"] == frozen["terminal_ledger_sha256"]


def test_complete_v113_report_checksum_and_locked_protocol() -> None:
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    expected = (RESULT / "report.json.sha256").read_text(encoding="utf-8").split()[0]
    actual = hashlib.sha256((RESULT / "report.json").read_bytes()).hexdigest()

    assert actual == expected == frozen["report_sha256"]
    assert frozen["splits"]["locked"] == {
        "attempts": 2,
        "successes": 1,
        "pass_at_1": 0.5,
        "one_shot": True,
        "retried": False,
        "workflow_run": 39584933038,
    }
