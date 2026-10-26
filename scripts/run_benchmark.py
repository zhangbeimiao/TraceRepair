"""Run a frozen multi-repository pass@1 benchmark and preserve every attempt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tracerepair.benchmark_suite import (
    BenchmarkManifest,
    BenchmarkManifestError,
    BenchmarkTask,
    append_ledger_record,
    build_report,
    read_ledger,
    write_report,
)
from tracerepair.evaluation_report import RunMetrics, TraceEvaluator
from tracerepair.oracle_validation import OracleValidationError, validate_historical_oracles
from tracerepair.repository_task import RepositoryTaskSpec
from tracerepair.version import AGENT_VERSION, MAX_MODEL_CALLS, MODEL_ID


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--split",
        choices=("all", "development", "locked"),
        default="all",
        help="run all pending tasks or one predeclared split",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and hash every task without calling the model",
    )
    parser.add_argument(
        "--process-timeout-seconds",
        type=int,
        default=300,
        help="outer per-task timeout from 30 to 900 seconds",
    )
    arguments = parser.parse_args()
    if not 30 <= arguments.process_timeout_seconds <= 900:
        parser.error("--process-timeout-seconds must be between 30 and 900")
    if os.name == "nt" and ROOT.drive.casefold() != "d:":
        raise SystemExit("TraceRepair benchmark artifacts must remain on D: on this workstation")

    try:
        manifest = BenchmarkManifest.load(arguments.manifest)
        _validate_runtime(manifest)
        selected = tuple(
            task
            for task in manifest.tasks
            if arguments.split == "all" or task.split == arguments.split
        )
        if not selected:
            raise BenchmarkManifestError("the selected split contains no benchmark tasks")
        result_root = ROOT / "evaluation" / "results" / manifest.benchmark_id
        ledger_path = result_root / "attempts.jsonl"
        report_path = result_root / "report.json"
        records = read_ledger(ledger_path)
        _reject_manifest_reuse(records, manifest)
        attempted = {
            str(record.get("benchmark_task_id"))
            for record in records
            if record.get("benchmark_id") == manifest.benchmark_id
            and record.get("manifest_sha256") == manifest.manifest_sha256
        }
        pending = tuple(task for task in selected if task.task_id not in attempted)
        if not pending and not arguments.dry_run:
            _print_preflight(manifest, selected, pending, result_root)
            _write_or_verify_lock(result_root / "manifest.lock.json", manifest)
            report = _load_or_finalize_report(report_path, manifest, records)
            print(
                "No pending tasks: verified the existing ledger and report without "
                "rerunning oracle or model calls."
            )
            _print_benchmark_result(manifest, report, ledger_path, report_path)
            return
        oracle_results = validate_historical_oracles(manifest, selected, ROOT)
        print("Historical oracle preflight")
        for result in oracle_results:
            print(
                f"- {result.task_id}: buggy_exit={result.buggy_exit_code} "
                f"fixed_target={result.fixed_target_passed} "
                f"fixed_regression={result.fixed_regression_passed}"
            )
        _print_preflight(manifest, selected, pending, result_root)
        if arguments.dry_run:
            print(
                "Dry run completed: disposable oracle workspaces were removed, no benchmark "
                "result was written, and no provider request was made."
            )
            return
        _write_or_verify_lock(result_root / "manifest.lock.json", manifest)
        if pending and (
            not os.getenv("DASHSCOPE_API_KEY")
            or not os.getenv("TRACEREPAIR_BAILIAN_BASE_URL")
        ):
            raise SystemExit(
                "Bailian environment variables are not configured. The manifest was locked, "
                "but no benchmark task was attempted."
            )
        print(
            f"Maximum provider requests in this command: "
            f"{len(pending) * MAX_MODEL_CALLS}."
        )
        for index, task in enumerate(pending, start=1):
            print(f"\n=== pass@1 task {index}/{len(pending)}: {task.task_id} ===")
            _run_task(
                manifest,
                task,
                ledger_path,
                result_root,
                process_timeout=arguments.process_timeout_seconds,
            )
        records = read_ledger(ledger_path)
        report = build_report(manifest, records)
        write_report(report_path, report)
        _print_benchmark_result(manifest, report, ledger_path, report_path)
    except (BenchmarkManifestError, OracleValidationError) as error:
        raise SystemExit(f"Benchmark rejected safely: {error}") from error


def _validate_runtime(manifest: BenchmarkManifest) -> None:
    if manifest.agent_version != AGENT_VERSION:
        raise BenchmarkManifestError(
            f"manifest agent {manifest.agent_version} does not match runtime {AGENT_VERSION}"
        )
    if manifest.model != MODEL_ID:
        raise BenchmarkManifestError(
            f"manifest model {manifest.model} does not match runtime {MODEL_ID}"
        )


def _reject_manifest_reuse(
    records: list[dict[str, object]], manifest: BenchmarkManifest
) -> None:
    conflicting = [
        record
        for record in records
        if record.get("benchmark_id") == manifest.benchmark_id
        and record.get("manifest_sha256") != manifest.manifest_sha256
    ]
    if conflicting:
        raise BenchmarkManifestError(
            "benchmark_id already has attempts for a different manifest hash; use a new id"
        )


def _write_or_verify_lock(path: Path, manifest: BenchmarkManifest) -> None:
    benchmark = manifest.lock_payload()
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BenchmarkManifestError("existing manifest lock is unreadable") from error
        if not isinstance(existing, dict) or existing.get("benchmark") != benchmark:
            raise BenchmarkManifestError("existing manifest lock does not match current inputs")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "locked_at": datetime.now(UTC).isoformat(),
        "benchmark": benchmark,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _load_or_finalize_report(
    path: Path,
    manifest: BenchmarkManifest,
    records: list[dict[str, object]],
) -> dict[str, object]:
    """Return a completed report without mutating an already published artifact."""

    reconstructed = build_report(manifest, records)
    if not path.exists():
        write_report(path, reconstructed)
        return reconstructed
    checksum_path = path.with_suffix(path.suffix + ".sha256")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        expected = checksum_path.read_text(encoding="utf-8").split()[0]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, IndexError) as error:
        raise BenchmarkManifestError("existing completed report is unreadable") from error
    if not isinstance(payload, dict):
        raise BenchmarkManifestError("existing completed report root is invalid")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise BenchmarkManifestError("existing completed report checksum mismatch")
    for key in ("benchmark", "attempts", "summary", "integrity"):
        if payload.get(key) != reconstructed.get(key):
            raise BenchmarkManifestError(
                f"existing completed report does not match the verified ledger: {key}"
            )
    return payload


def _print_benchmark_result(
    manifest: BenchmarkManifest,
    report: dict[str, object],
    ledger_path: Path,
    report_path: Path,
) -> None:
    summary = report["summary"]
    assert isinstance(summary, dict)
    print("\n=== benchmark result ===")
    print(
        f"benchmark={manifest.benchmark_id} attempted={summary['attempted_tasks']}/"
        f"{summary['expected_tasks']} successes={summary['successes']} "
        f"pass@1={float(summary['pass_at_1']):.2%} failures={summary['failures']}"
    )
    print(
        f"p50={summary['p50_wall_seconds']}s p95={summary['p95_wall_seconds']}s "
        f"avg_completion_tokens={summary['average_completion_tokens']} "
        f"estimated_completion_cost_cny={summary['estimated_completion_cost_cny']}"
    )
    print(f"Tamper-evident ledger: {ledger_path.relative_to(ROOT)}")
    print(f"Frozen report: {report_path.relative_to(ROOT)}")
    print(f"Report checksum: {report_path.relative_to(ROOT)}.sha256")


def _print_preflight(
    manifest: BenchmarkManifest,
    selected: tuple[BenchmarkTask, ...],
    pending: tuple[BenchmarkTask, ...],
    result_root: Path,
) -> None:
    print("TraceRepair historical benchmark preflight")
    print(
        f"benchmark={manifest.benchmark_id} protocol={manifest.protocol} "
        f"agent={manifest.agent_version} model={manifest.model}"
    )
    print(f"manifest_sha256={manifest.manifest_sha256}")
    print(f"selected={len(selected)} pending={len(pending)} results={result_root}")
    pending_ids = {task.task_id for task in pending}
    for task in selected:
        state = "pending" if task.task_id in pending_ids else "already-attempted"
        print(
            f"- {task.task_id} split={task.split} state={state} "
            f"config={task.config_sha256[:12]} repo={task.repository_sha256[:12]}"
        )


def _run_task(
    manifest: BenchmarkManifest,
    task: BenchmarkTask,
    ledger_path: Path,
    result_root: Path,
    *,
    process_timeout: int,
) -> None:
    spec = RepositoryTaskSpec.load(task.config_path)
    database = ROOT / "data" / "model-agent.sqlite3"
    before = _task_ids(database, f"repo-{spec.name}")
    source = as_source_payload(task)
    started_record = append_ledger_record(
        ledger_path,
        {
            "record_kind": "attempt_started",
            "benchmark_id": manifest.benchmark_id,
            "manifest_sha256": manifest.manifest_sha256,
            "benchmark_task_id": task.task_id,
            "split": task.split,
            "task_config_sha256": task.config_sha256,
            "repository_sha256": task.repository_sha256,
            "source": source,
        },
    )
    environment = os.environ.copy()
    environment["TEMP"] = str(ROOT / "tmp")
    environment["TMP"] = str(ROOT / "tmp")
    environment["PYTHONPYCACHEPREFIX"] = str(ROOT / ".cache" / "pycache")
    started = time.monotonic()
    timed_out = False
    process_returncode: int | None = None
    stdout = ""
    stderr = ""
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "model_repair_agent.py"),
                "--task",
                str(task.config_path),
            ],
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=process_timeout,
        )
        process_returncode = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as error:
        timed_out = True
        stdout = _timeout_text(error.stdout)
        stderr = _timeout_text(error.stderr)
    wall_seconds = round(time.monotonic() - started, 3)
    output = _redact_output(stdout + ("\n" if stdout and stderr else "") + stderr)
    if output:
        print(output.rstrip())
    after_runs = _matching_runs(database, f"repo-{spec.name}")
    new_runs = [run for run in after_runs if run.task_id not in before]
    run = new_runs[-1] if len(new_runs) == 1 else None
    if len(new_runs) > 1:
        raise BenchmarkManifestError(
            f"multiple trace tasks appeared while running {task.task_id}; refusing attribution"
        )
    if timed_out:
        status = "process_timeout"
        stop_reason = f"outer process timeout after {process_timeout} seconds"
    elif run is None:
        status = "process_error"
        stop_reason = f"runner exited {process_returncode} without a trace task"
    else:
        status = run.status
        stop_reason = run.stop_reason
    log_path = result_root / "logs" / f"{task.task_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(output, encoding="utf-8", newline="\n")
    record: dict[str, object] = {
        "record_kind": "attempt_finished",
        "attempt_started_record_sha256": started_record["record_sha256"],
        "benchmark_id": manifest.benchmark_id,
        "manifest_sha256": manifest.manifest_sha256,
        "benchmark_task_id": task.task_id,
        "split": task.split,
        "task_config_sha256": task.config_sha256,
        "repository_sha256": task.repository_sha256,
        "source": source,
        "trace_task_id": run.task_id if run else None,
        "process_returncode": process_returncode,
        "timed_out": timed_out,
        "wall_seconds": wall_seconds,
        "status": status,
        "success": run.end_to_end_success if run else False,
        "model_calls": run.model_calls if run else 0,
        "completion_tokens": run.completion_tokens if run else 0,
        "tool_calls": run.tool_calls if run else 0,
        "tool_failures": run.tool_failures if run else 0,
        "target_test_passed": run.target_test_passed if run else False,
        "regression_passed": run.regression_passed if run else False,
        "stop_reason": stop_reason,
        "log_path": log_path.relative_to(ROOT).as_posix(),
        "log_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
    }
    appended = append_ledger_record(ledger_path, record)
    print(
        f"Recorded sequence={appended['sequence']} success={record['success']} "
        f"status={status} wall={wall_seconds}s hash={str(appended['record_sha256'])[:12]}"
    )


def _task_ids(database: Path, case_id: str) -> set[str]:
    return {run.task_id for run in _matching_runs(database, case_id)}


def _matching_runs(database: Path, case_id: str) -> list[RunMetrics]:
    if not database.is_file():
        return []
    evaluator = TraceEvaluator(database)
    try:
        return evaluator.runs(
            task_prefix="model-agent-repo-",
            agent_version=AGENT_VERSION,
            case_id=case_id,
        )
    finally:
        evaluator.close()


def as_source_payload(task: BenchmarkTask) -> dict[str, object]:
    return {
        "repository_url": task.source.repository_url,
        "buggy_commit": task.source.buggy_commit,
        "fixed_commit": task.source.fixed_commit,
        "issue_url": task.source.issue_url,
    }


def _timeout_text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


def _redact_output(value: str) -> str:
    redacted = value
    for variable in ("DASHSCOPE_API_KEY",):
        secret = os.getenv(variable)
        if secret:
            redacted = redacted.replace(secret, "<redacted>")
    return re.sub(r"sk-[A-Za-z0-9._-]{12,}", "<redacted-key>", redacted)


if __name__ == "__main__":
    main()
