import json
from pathlib import Path

import pytest

from scripts.run_benchmark import _load_or_finalize_report
from tracerepair.benchmark_suite import (
    BenchmarkManifest,
    BenchmarkManifestError,
    append_ledger_record,
    build_report,
    read_ledger,
    write_report,
)


def _repository(root: Path, name: str) -> Path:
    repository = root / name
    (repository / "src" / name).mkdir(parents=True)
    (repository / "tests").mkdir()
    (repository / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\npythonpath = ['src']\n", encoding="utf-8"
    )
    (repository / "src" / name / "logic.py").write_text(
        "def value():\n    return 1\n", encoding="utf-8"
    )
    (repository / "tests" / "test_logic.py").write_text(
        f"from {name}.logic import value\n\ndef test_value():\n    assert value() == 2\n",
        encoding="utf-8",
    )
    return repository


def _task(path: Path, repository: Path, name: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": name,
                "repository_root": str(repository),
                "issue": "value returns one instead of two",
                "source_allowlist": [f"src/{repository.name}"],
                "target_test": "tests/test_logic.py::test_value",
                "regression_suite": "tests",
                "diagnostic_queries": ["def value"],
                "pythonpath": ["src"],
            }
        ),
        encoding="utf-8",
    )


def _manifest(tmp_path: Path) -> Path:
    first_repo = _repository(tmp_path, "alpha")
    second_repo = _repository(tmp_path, "beta")
    first_task = tmp_path / "alpha.json"
    second_task = tmp_path / "beta.json"
    _task(first_task, first_repo, "alpha-value")
    _task(second_task, second_repo, "beta-value")
    path = tmp_path / "benchmark.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "benchmark_id": "historical-v0.7-test",
                "agent_version": "0.4.0-dev1",
                "model": "qwen3.8-flash",
                "protocol": "pass@1",
                "completion_cny_per_million_tokens": 0.8,
                "tasks": [
                    {
                        "id": "alpha-value",
                        "split": "development",
                        "task_config": "alpha.json",
                        "source": {
                            "repository_url": "https://github.com/example/alpha",
                            "buggy_commit": "a" * 40,
                            "fixed_commit": "b" * 40,
                        },
                    },
                    {
                        "id": "beta-value",
                        "split": "locked",
                        "task_config": "beta.json",
                        "source": {
                            "repository_url": "https://github.com/example/beta",
                            "buggy_commit": "c" * 40,
                            "fixed_commit": "d" * 40,
                            "issue_url": "https://github.com/example/beta/issues/1",
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_manifest_freezes_configs_repositories_and_sources(tmp_path: Path) -> None:
    manifest = BenchmarkManifest.load(_manifest(tmp_path))

    assert manifest.protocol == "pass@1"
    assert len(manifest.tasks) == 2
    assert len(manifest.manifest_sha256) == 64
    assert all(len(task.config_sha256) == 64 for task in manifest.tasks)
    assert all(len(task.repository_sha256) == 64 for task in manifest.tasks)
    assert manifest.tasks[1].split == "locked"


def test_ledger_detects_modified_historical_result(tmp_path: Path) -> None:
    path = tmp_path / "attempts.jsonl"
    append_ledger_record(path, {"benchmark_task_id": "alpha-value", "success": False})
    append_ledger_record(path, {"benchmark_task_id": "beta-value", "success": True})
    assert len(read_ledger(path)) == 2

    content = path.read_text(encoding="utf-8").replace(
        '"success": false', '"success": true', 1
    )
    path.write_text(content, encoding="utf-8")

    with pytest.raises(BenchmarkManifestError, match="content mismatch"):
        read_ledger(path)


def test_report_keeps_failures_latency_cost_and_checksum(tmp_path: Path) -> None:
    manifest = BenchmarkManifest.load(_manifest(tmp_path))
    ledger = tmp_path / "attempts.jsonl"
    common = {
        "benchmark_id": manifest.benchmark_id,
        "manifest_sha256": manifest.manifest_sha256,
        "completion_tokens": 100,
        "regression_passed": True,
    }
    append_ledger_record(
        ledger,
        {
            **common,
            "benchmark_task_id": "alpha-value",
            "success": True,
            "status": "awaiting_review",
            "wall_seconds": 1.0,
            "stop_reason": "verified",
        },
    )
    append_ledger_record(
        ledger,
        {
            **common,
            "benchmark_task_id": "beta-value",
            "success": False,
            "status": "needs_human",
            "regression_passed": False,
            "wall_seconds": 3.0,
            "stop_reason": "candidate patch rejected",
        },
    )

    report = build_report(manifest, read_ledger(ledger))
    output = tmp_path / "report.json"
    write_report(output, report)

    assert report["summary"]["pass_at_1"] == 0.5
    assert report["summary"]["failures"] == 1
    assert report["summary"]["human_handoffs"] == 1
    assert report["summary"]["p50_wall_seconds"] == 1.0
    assert report["summary"]["p95_wall_seconds"] == 3.0
    assert report["summary"]["estimated_completion_cost_cny"] == 0.00016
    assert report["attempts"][1]["stop_reason"] == "candidate patch rejected"
    assert output.with_suffix(".json.sha256").is_file()


def test_started_attempt_without_result_counts_as_failure_and_is_not_missing(
    tmp_path: Path,
) -> None:
    manifest = BenchmarkManifest.load(_manifest(tmp_path))
    ledger = tmp_path / "attempts.jsonl"
    append_ledger_record(
        ledger,
        {
            "record_kind": "attempt_started",
            "benchmark_id": manifest.benchmark_id,
            "manifest_sha256": manifest.manifest_sha256,
            "benchmark_task_id": "alpha-value",
        },
    )

    report = build_report(manifest, read_ledger(ledger))

    assert report["summary"]["attempted_tasks"] == 1
    assert report["summary"]["failures"] == 1
    assert report["summary"]["missing_task_ids"] == ["beta-value"]
    assert report["attempts"][0]["status"] == "interrupted_before_result_record"


def test_completed_report_is_verified_without_being_rewritten(tmp_path: Path) -> None:
    manifest = BenchmarkManifest.load(_manifest(tmp_path))
    ledger = tmp_path / "attempts.jsonl"
    for task in manifest.tasks:
        append_ledger_record(
            ledger,
            {
                "record_kind": "attempt_finished",
                "benchmark_id": manifest.benchmark_id,
                "manifest_sha256": manifest.manifest_sha256,
                "benchmark_task_id": task.task_id,
                "success": True,
                "status": "awaiting_review",
                "wall_seconds": 1.0,
                "completion_tokens": 10,
                "regression_passed": True,
                "stop_reason": "verified",
            },
        )
    records = read_ledger(ledger)
    path = tmp_path / "report.json"
    write_report(path, build_report(manifest, records))
    before = path.read_bytes()

    loaded = _load_or_finalize_report(path, manifest, records)

    assert loaded["summary"]["attempted_tasks"] == 2
    assert path.read_bytes() == before


def test_completed_report_checksum_mismatch_is_rejected(tmp_path: Path) -> None:
    manifest = BenchmarkManifest.load(_manifest(tmp_path))
    path = tmp_path / "report.json"
    write_report(path, build_report(manifest, []))
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(BenchmarkManifestError, match="checksum mismatch"):
        _load_or_finalize_report(path, manifest, [])
