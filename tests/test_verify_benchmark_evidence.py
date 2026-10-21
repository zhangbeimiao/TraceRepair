import shutil
from pathlib import Path

import pytest

from scripts.verify_benchmark_evidence import verify_evidence
from tracerepair.benchmark_suite import BenchmarkManifestError


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = "historical-python-v1.1.3"


def test_published_v113_evidence_verifies_without_execution() -> None:
    result = verify_evidence(ROOT, benchmark_id=BENCHMARK)

    assert result["release_agent_version"] == "0.6.0"
    assert result["tasks"] == 5
    assert result["successes"] == 3
    assert result["ledger_records"] == 10


def test_modified_ledger_is_rejected(tmp_path: Path) -> None:
    for relative in (
        f"evaluation/frozen/{BENCHMARK}.json",
        f"evaluation/frozen/{BENCHMARK}.json.sha256",
        "evaluation/frozen/agent-v0.6.0.json",
        "evaluation/configs/agent-v0.6.0-dev4.json",
        f"evaluation/benchmarks/{BENCHMARK}.json",
        f"evaluation/results/{BENCHMARK}/attempts.jsonl",
        f"evaluation/results/{BENCHMARK}/report.json",
        f"evaluation/results/{BENCHMARK}/report.json.sha256",
    ):
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    ledger = tmp_path / "evaluation" / "results" / BENCHMARK / "attempts.jsonl"
    ledger.write_text(
        ledger.read_text(encoding="utf-8").replace('"success": false', '"success": true', 1),
        encoding="utf-8",
    )

    with pytest.raises((ValueError, BenchmarkManifestError), match="ledger"):
        verify_evidence(tmp_path, benchmark_id=BENCHMARK)
