"""Verify frozen benchmark evidence without network, model calls, or test execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tracerepair.benchmark_suite import BenchmarkManifestError, read_ledger


def _json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _checksum(path: Path) -> str:
    return path.read_text(encoding="ascii").split()[0]


def verify_evidence(
    root: Path = ROOT,
    *,
    benchmark_id: str = "historical-python-v1.1.3",
) -> dict[str, Any]:
    frozen_path = root / "evaluation" / "frozen" / f"{benchmark_id}.json"
    frozen_checksum_path = frozen_path.with_suffix(".json.sha256")
    results = root / "evaluation" / "results" / benchmark_id
    report_path = results / "report.json"
    report_checksum_path = results / "report.json.sha256"
    ledger_path = results / "attempts.jsonl"
    manifest_path = root / "evaluation" / "benchmarks" / f"{benchmark_id}.json"

    required = (
        frozen_path,
        frozen_checksum_path,
        report_path,
        report_checksum_path,
        ledger_path,
        manifest_path,
    )
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    if missing:
        raise ValueError("missing evidence files: " + ", ".join(missing))

    frozen = _json(frozen_path)
    report = _json(report_path)
    if frozen.get("benchmark_id") != benchmark_id:
        raise ValueError("frozen benchmark id does not match the requested id")
    if _sha256(frozen_path) != _checksum(frozen_checksum_path):
        raise ValueError("frozen summary checksum mismatch")
    report_file_sha = _sha256(report_path)
    if report_file_sha != _checksum(report_checksum_path):
        raise ValueError("report checksum file does not match report bytes")
    if report_file_sha != frozen.get("report_sha256"):
        raise ValueError("frozen report checksum does not match report bytes")
    if _sha256(manifest_path) != frozen.get("manifest_sha256"):
        raise ValueError("manifest checksum does not match the frozen summary")

    release_agent = str(frozen.get("release_agent_version", ""))
    if not release_agent:
        raise ValueError("frozen summary is missing release_agent_version")
    agent_path = root / "evaluation" / "frozen" / f"agent-v{release_agent}.json"
    agent = _json(agent_path)
    config = agent.get("configuration")
    if not isinstance(config, dict) or not isinstance(config.get("path"), str):
        raise ValueError("frozen agent configuration reference is invalid")
    config_path = root / str(config["path"])
    config_sha = _sha256(config_path)
    if config_sha != config.get("sha256") or config_sha != frozen.get("agent_config_sha256"):
        raise ValueError("agent configuration checksum mismatch")

    records = read_ledger(ledger_path)
    if not records:
        raise ValueError("benchmark ledger is empty")
    if records[-1].get("record_sha256") != frozen.get("terminal_ledger_sha256"):
        raise ValueError("terminal ledger hash does not match the frozen summary")

    kinds = Counter(str(record.get("record_kind")) for record in records)
    summary = frozen.get("summary")
    attempts = frozen.get("attempts")
    if not isinstance(summary, dict) or not isinstance(attempts, list):
        raise ValueError("frozen summary is incomplete")
    expected_tasks = int(summary.get("attempted_tasks", 0))
    if kinds != {"attempt_started": expected_tasks, "attempt_finished": expected_tasks}:
        raise ValueError("ledger does not contain exactly one start and finish per task")

    finished = {
        str(record.get("benchmark_task_id")): record
        for record in records
        if record.get("record_kind") == "attempt_finished"
    }
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise ValueError("frozen attempt entry is invalid")
        task_id = str(attempt.get("task_id"))
        record = finished.get(task_id)
        if record is None or record.get("record_sha256") != attempt.get("record_sha256"):
            raise ValueError(f"frozen attempt hash mismatch: {task_id}")
        if record.get("success") is not attempt.get("success"):
            raise ValueError(f"frozen attempt outcome mismatch: {task_id}")

    report_summary = report.get("summary")
    if not isinstance(report_summary, dict):
        raise ValueError("report summary is invalid")
    for key in (
        "attempted_tasks",
        "successes",
        "failures",
        "pass_at_1",
        "human_handoffs",
        "incorrect_accepted_patches",
        "average_completion_tokens",
        "total_completion_tokens",
        "p50_wall_seconds",
        "p95_wall_seconds",
        "wilson_95_percent",
    ):
        if report_summary.get(key) != summary.get(key):
            raise ValueError(f"report and frozen summary disagree on {key}")
    integrity = report.get("integrity")
    if not isinstance(integrity, dict) or integrity.get("terminal_record_sha256") != frozen.get(
        "terminal_ledger_sha256"
    ):
        raise ValueError("report terminal ledger hash mismatch")

    return {
        "benchmark_id": benchmark_id,
        "release_agent_version": release_agent,
        "tasks": expected_tasks,
        "successes": int(summary["successes"]),
        "pass_at_1": summary["pass_at_1"],
        "ledger_records": len(records),
        "report_sha256": report_file_sha,
        "terminal_ledger_sha256": frozen["terminal_ledger_sha256"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", default="historical-python-v1.1.3")
    arguments = parser.parse_args()
    try:
        result = verify_evidence(benchmark_id=arguments.benchmark)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, BenchmarkManifestError) as error:
        raise SystemExit(f"Frozen benchmark verification failed: {error}") from error
    print("Frozen benchmark evidence verified.")
    print(
        f"benchmark={result['benchmark_id']} agent={result['release_agent_version']} "
        f"pass@1={result['successes']}/{result['tasks']} ledger_records={result['ledger_records']}"
    )
    print(f"report_sha256={result['report_sha256']}")
    print(f"terminal_ledger_sha256={result['terminal_ledger_sha256']}")


if __name__ == "__main__":
    main()
