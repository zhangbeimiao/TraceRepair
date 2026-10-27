"""Verify both locked blind cohorts and their six-repository aggregate offline."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.verify_benchmark_evidence import verify_evidence


COHORTS = (
    "langgraph-blind-v0.7.0-dev2",
    "langgraph-blind-extension-v0.7.0-dev2",
)
AGGREGATE = "langgraph-blind-six-repository-v0.7.0-dev2"


def _json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _checksum(path: Path) -> str:
    return path.read_text(encoding="ascii").split()[0]


def _percentile(values: list[float], fraction: float) -> float:
    values = sorted(values)
    rank = max(1, math.ceil(fraction * len(values)))
    return round(values[rank - 1], 3)


def _wilson(successes: int, total: int) -> dict[str, float]:
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
        / denominator
    )
    return {
        "lower": round(max(0.0, centre - margin), 4),
        "upper": round(min(1.0, centre + margin), 4),
    }


def verify_blind_evidence(root: Path = ROOT) -> dict[str, Any]:
    aggregate_path = root / "evaluation" / "frozen" / f"{AGGREGATE}.json"
    aggregate_checksum = aggregate_path.with_suffix(".json.sha256")
    if _sha256(aggregate_path) != _checksum(aggregate_checksum):
        raise ValueError("six-repository aggregate checksum mismatch")
    aggregate = _json(aggregate_path)
    if aggregate.get("evidence_type") != "aggregate_index_over_two_independently_sealed_cohorts":
        raise ValueError("unexpected aggregate evidence type")

    successes = failures = handoffs = incorrect = tokens = model_calls = tool_calls = 0
    durations: list[float] = []
    task_ids: set[str] = set()
    cohort_results = []
    for benchmark_id in COHORTS:
        cohort_result = verify_evidence(root, benchmark_id=benchmark_id)
        cohort_results.append(cohort_result)
        frozen_path = root / "evaluation" / "frozen" / f"{benchmark_id}.json"
        frozen = _json(frozen_path)
        report = _json(root / "evaluation" / "results" / benchmark_id / "report.json")
        attempts = report.get("attempts")
        if not isinstance(attempts, list) or len(attempts) != 3:
            raise ValueError(f"{benchmark_id} must contain exactly three attempts")
        for attempt in attempts:
            if not isinstance(attempt, dict):
                raise ValueError("invalid blind attempt")
            task_id = str(attempt.get("benchmark_task_id"))
            if task_id in task_ids:
                raise ValueError(f"duplicate blind task: {task_id}")
            task_ids.add(task_id)
            successes += attempt.get("success") is True
            failures += attempt.get("success") is not True
            handoffs += attempt.get("status") == "needs_human"
            incorrect += (
                attempt.get("status") in {"awaiting_review", "succeeded"}
                and attempt.get("regression_passed") is not True
            )
            tokens += int(attempt.get("completion_tokens", 0))
            model_calls += int(attempt.get("model_calls", 0))
            tool_calls += int(attempt.get("tool_calls", 0))
            durations.append(float(attempt.get("wall_seconds", 0)))

        cohort_ref = next(
            item
            for item in aggregate["cohorts"]
            if item.get("benchmark_id") == benchmark_id
        )
        if cohort_ref.get("frozen_summary_sha256") != _sha256(frozen_path):
            raise ValueError(f"aggregate frozen hash mismatch: {benchmark_id}")
        if cohort_ref.get("report_sha256") != frozen.get("report_sha256"):
            raise ValueError(f"aggregate report hash mismatch: {benchmark_id}")
        if cohort_ref.get("terminal_ledger_sha256") != frozen.get("terminal_ledger_sha256"):
            raise ValueError(f"aggregate ledger hash mismatch: {benchmark_id}")

    total = successes + failures
    expected = {
        "repositories": total,
        "attempts": total,
        "successes": successes,
        "failures": failures,
        "pass_at_1": round(successes / total, 4),
        "human_handoffs": handoffs,
        "incorrect_accepted_patches": incorrect,
        "total_completion_tokens": tokens,
        "average_completion_tokens": round(tokens / total, 2),
        "total_model_calls": model_calls,
        "average_model_calls": round(model_calls / total, 2),
        "total_tool_calls": tool_calls,
        "average_tool_calls": round(tool_calls / total, 2),
        "p50_wall_seconds": _percentile(durations, 0.50),
        "p95_wall_seconds": _percentile(durations, 0.95),
        "wilson_95_percent": _wilson(successes, total),
    }
    if aggregate.get("summary") != expected:
        raise ValueError("six-repository aggregate metrics do not match cohort evidence")
    if len(task_ids) != 6 or len(aggregate.get("attempts", [])) != 6:
        raise ValueError("six-repository aggregate does not contain six distinct tasks")
    return {
        "evidence_id": AGGREGATE,
        "tasks": total,
        "successes": successes,
        "human_handoffs": handoffs,
        "incorrect_accepted_patches": incorrect,
        "aggregate_sha256": _sha256(aggregate_path),
        "cohorts": cohort_results,
    }


def main() -> None:
    try:
        result = verify_blind_evidence()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        raise SystemExit(f"Blind evidence verification failed: {error}") from error
    print("Six-repository blind evidence verified.")
    print(
        f"agent=0.7.0-dev2 pass@1={result['successes']}/{result['tasks']} "
        f"handoffs={result['human_handoffs']} "
        f"incorrect_accepted={result['incorrect_accepted_patches']}"
    )
    print(f"aggregate_sha256={result['aggregate_sha256']}")
    for cohort in result["cohorts"]:
        print(
            f"cohort={cohort['benchmark_id']} report={cohort['report_sha256']} "
            f"ledger={cohort['terminal_ledger_sha256']}"
        )


if __name__ == "__main__":
    main()
