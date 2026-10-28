"""Compare format-contract failures on paired development benchmark reports."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = (
    ROOT / "evaluation" / "results" / "langgraph-review-offline-v0.7.0-dev2" / "report.json"
)
DEFAULT_NATIVE = (
    ROOT / "evaluation" / "results" / "function-calling-v0.8.0-dev1.1" / "report.json"
)
DEFAULT_OUTPUT = (
    ROOT / "evaluation" / "results" / "function-calling-v0.8.0-dev1.1" / "protocol-comparison.json"
)
FORMAT_MARKERS = (
    "invalid structured output",
    "reason is invalid",
    "no native function call",
    "invalid function-call envelope",
    "invalid function arguments",
    "exactly one native function call",
    "unknown function",
    "omitted required function arguments",
    "unknown function arguments",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--native", type=Path, default=DEFAULT_NATIVE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    baseline = _load_report(arguments.baseline)
    native = _load_report(arguments.native)
    baseline_ids = _task_ids(baseline)
    native_ids = _task_ids(native)
    if baseline_ids != native_ids:
        raise SystemExit(
            "paired comparison requires identical task ids; "
            f"baseline_only={sorted(baseline_ids - native_ids)} "
            f"native_only={sorted(native_ids - baseline_ids)}"
        )
    payload = {
        "schema_version": 1,
        "comparison_id": "custom-json-vs-native-functions-v0.8.0-dev1.1",
        "split": "known_development_tasks",
        "paired_task_ids": sorted(baseline_ids),
        "baseline": _metrics(baseline, "custom_json", arguments.baseline),
        "candidate": _metrics(native, "native_function_calling", arguments.native),
        "interpretation_boundary": (
            "This is a paired development-set protocol comparison, not locked generalisation "
            "evidence. Format-contract failures are separated from test-gated repair failures."
        ),
    }
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    output = arguments.output.resolve()
    if not output.is_relative_to(ROOT.resolve()) or output.drive.casefold() == "c:":
        raise SystemExit("comparison output must remain inside the D: project")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encoded)
    digest = hashlib.sha256(encoded).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{digest}  {output.name}\n", encoding="ascii", newline="\n"
    )
    print("Planner protocol comparison written.")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"SHA-256: {digest}")


def _load_report(path: Path) -> dict[str, object]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise SystemExit(f"benchmark report is missing: {resolved}")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"benchmark report is unreadable: {resolved}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("attempts"), list):
        raise SystemExit(f"benchmark report has an invalid structure: {resolved}")
    return payload


def _task_ids(report: dict[str, object]) -> set[str]:
    return {str(row["benchmark_task_id"]) for row in report["attempts"]}  # type: ignore[index]


def _metrics(report: dict[str, object], protocol: str, source: Path) -> dict[str, object]:
    attempts = report["attempts"]
    assert isinstance(attempts, list)
    format_failures = [
        str(row.get("benchmark_task_id"))
        for row in attempts
        if isinstance(row, dict) and _is_format_failure(str(row.get("stop_reason", "")))
    ]
    successes = sum(isinstance(row, dict) and row.get("success") is True for row in attempts)
    return {
        "planner_protocol": protocol,
        "source_report": source.resolve().relative_to(ROOT.resolve()).as_posix(),
        "source_report_sha256": hashlib.sha256(source.resolve().read_bytes()).hexdigest(),
        "attempts": len(attempts),
        "successes": successes,
        "pass_at_1": round(successes / len(attempts), 4) if attempts else 0.0,
        "format_contract_failures": len(format_failures),
        "format_failure_rate": round(len(format_failures) / len(attempts), 4)
        if attempts
        else 0.0,
        "format_failure_task_ids": format_failures,
    }


def _is_format_failure(reason: str) -> bool:
    compact = reason.casefold()
    return any(marker in compact for marker in FORMAT_MARKERS)


if __name__ == "__main__":
    main()
