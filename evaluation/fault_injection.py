"""Run deterministic fault-injection evidence without a model provider."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SUITE_ROOT = ROOT / "evaluation" / "fault_suites"


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _suite_path(suite_id: str) -> Path:
    if not suite_id or any(part in suite_id for part in ("/", "\\", "..")):
        raise ValueError("suite must be a simple identifier")
    path = SUITE_ROOT / f"{suite_id}.json"
    if not path.is_file():
        raise ValueError(f"unknown fault-injection suite: {suite_id}")
    return path


def load_suite(suite_id: str) -> dict[str, Any]:
    path = _suite_path(suite_id)
    suite = json.loads(path.read_text(encoding="utf-8"))
    if suite.get("schema_version") != 1 or suite.get("suite_id") != suite_id:
        raise ValueError("fault-injection suite schema is invalid")
    scenarios = suite.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("fault-injection suite has no scenarios")
    identifiers: set[str] = set()
    for item in scenarios:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("fault-injection scenario is malformed")
        if item["id"] in identifiers:
            raise ValueError(f"duplicate scenario id: {item['id']}")
        identifiers.add(item["id"])
        selector = item.get("selector")
        if (
            not isinstance(selector, str)
            or not selector.startswith("tests/")
            or "::test_" not in selector
            or any(token in selector for token in (";", "|", "&", "`"))
        ):
            raise ValueError(f"unsafe pytest selector: {selector!r}")
        invariants = item.get("invariants")
        if not isinstance(invariants, list) or not invariants or not all(
            isinstance(value, str) and value for value in invariants
        ):
            raise ValueError(f"scenario has no invariants: {item['id']}")
    return suite


def run_suite(suite_id: str) -> dict[str, Any]:
    suite_path = _suite_path(suite_id)
    suite = load_suite(suite_id)
    results: list[dict[str, Any]] = []
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    for index, scenario in enumerate(suite["scenarios"], start=1):
        selector = str(scenario["selector"])
        print(f"[{index}/{len(suite['scenarios'])}] {scenario['id']}")
        started = time.perf_counter()
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", selector],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            check=False,
        )
        duration = round(time.perf_counter() - started, 3)
        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
        results.append(
            {
                "id": scenario["id"],
                "category": scenario["category"],
                "selector": selector,
                "passed": completed.returncode == 0,
                "exit_code": completed.returncode,
                "duration_seconds": duration,
                "invariants": scenario["invariants"],
                "stdout_sha256": _sha_bytes(completed.stdout),
                "stderr_sha256": _sha_bytes(completed.stderr),
                "stdout_tail": stdout[-1000:],
                "stderr_tail": stderr[-1000:],
            }
        )
    counts = Counter(str(item["category"]) for item in results)
    passed = sum(bool(item["passed"]) for item in results)
    source_paths = {
        "recovery": ROOT / "src" / "tracerepair" / "recovery.py",
        "workflow": ROOT / "src" / "tracerepair" / "workflow.py",
        "checkpoint_tests": ROOT / "tests" / "test_checkpoint_recovery.py",
        "invariant_tests": ROOT / "tests" / "test_repair_workflow.py",
    }
    return {
        "schema_version": 1,
        "suite_id": suite_id,
        "description": suite["description"],
        "execution": {
            "provider_requests": 0,
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "summary": {
            "scenarios": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "pass_rate": round(passed / len(results), 4),
            "categories": dict(sorted(counts.items())),
            "total_duration_seconds": round(
                sum(float(item["duration_seconds"]) for item in results), 3
            ),
        },
        "results": results,
        "integrity": {
            "suite_manifest_sha256": _sha_file(suite_path),
            "source_sha256": {name: _sha_file(path) for name, path in source_paths.items()},
        },
        "claim_boundary": (
            "These deterministic tests demonstrate the listed recovery and transition "
            "invariants for the exercised crash windows; they are not a proof against "
            "arbitrary hardware, filesystem, SQLite, or operating-system failures."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        f"# TraceRepair fault-injection evidence: {report['suite_id']}",
        "",
        report["description"],
        "",
        "## Summary",
        "",
        f"- Scenarios: **{summary['scenarios']}**",
        f"- Passed: **{summary['passed']}**",
        f"- Failed: **{summary['failed']}**",
        f"- Provider requests: **{report['execution']['provider_requests']}**",
        f"- Total test time: **{summary['total_duration_seconds']} seconds**",
        "",
        "## Scenarios",
        "",
        "| Scenario | Category | Result | Seconds | Enforced invariants |",
        "|---|---|---:|---:|---|",
    ]
    for result in report["results"]:
        invariants = "; ".join(result["invariants"]).replace("|", "\\|")
        lines.append(
            f"| {result['id']} | {result['category']} | "
            f"{'PASS' if result['passed'] else 'FAIL'} | "
            f"{result['duration_seconds']} | {invariants} |"
        )
    lines.extend(["", "## Claim boundary", "", report["claim_boundary"], ""])
    return "\n".join(lines)


def write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    output.write_bytes(encoded)
    output.with_suffix(".md").write_text(render_markdown(report), encoding="utf-8")
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{_sha_bytes(encoded)}  {output.name}\n", encoding="ascii"
    )


def default_output_path(suite_id: str) -> Path:
    """Return an ignored replay path so frozen evidence is never overwritten."""

    return ROOT / "runs" / f"fault-{suite_id}.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default="recovery_v1")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    suite = load_suite(args.suite)
    if args.dry_run:
        print(f"suite={args.suite} scenarios={len(suite['scenarios'])} provider_requests=0")
        for item in suite["scenarios"]:
            print(f"- {item['id']}: {item['selector']}")
        return
    report = run_suite(args.suite)
    # A normal replay must never overwrite checked-in frozen evidence because
    # measured durations and captured output hashes can legitimately change.
    # Maintainers may still pass --output explicitly when freezing a new suite.
    output = args.output or default_output_path(args.suite)
    write_report(report, output)
    summary = report["summary"]
    print(f"Fault-injection report written: {output.relative_to(ROOT)}")
    print(
        f"scenarios={summary['scenarios']} passed={summary['passed']} "
        f"failed={summary['failed']} provider_requests=0"
    )
    if summary["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
