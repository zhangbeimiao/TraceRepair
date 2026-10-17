"""Immutable summary rules for the one-shot locked evaluation split."""

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from tracerepair.evaluation_report import RunMetrics

_FINISHED_STATUSES = {
    "awaiting_review",
    "succeeded",
    "needs_human",
    "failed_safe",
    "blocked_policy",
}


@dataclass(frozen=True)
class LockedEvaluationSummary:
    case_ids: tuple[str, ...]
    agent_version: str
    runs: int
    successful_runs: int
    success_rate: float
    average_model_calls: float
    average_completion_tokens: float
    average_tool_calls: float
    stop_reasons: dict[str, int]
    run_counts: dict[str, int]
    complete: bool


def summarize_locked_evaluation(
    runs: list[RunMetrics],
    *,
    case_ids: tuple[str, ...],
    agent_version: str,
) -> LockedEvaluationSummary:
    if not case_ids or len(set(case_ids)) != len(case_ids):
        raise ValueError("case_ids must be non-empty and unique")
    matching = [
        run for run in runs if run.agent_version == agent_version and run.case_id in case_ids
    ]
    counts = {case_id: sum(run.case_id == case_id for run in matching) for case_id in case_ids}
    finished = all(run.status in _FINISHED_STATUSES for run in matching)
    complete = all(count == 1 for count in counts.values()) and finished
    run_count = len(matching)
    successes = sum(run.end_to_end_success for run in matching)

    def average(values: list[int]) -> float:
        return round(sum(values) / len(values), 2) if values else 0.0

    return LockedEvaluationSummary(
        case_ids=case_ids,
        agent_version=agent_version,
        runs=run_count,
        successful_runs=successes,
        success_rate=round(successes / run_count, 4) if run_count else 0.0,
        average_model_calls=average([run.model_calls for run in matching]),
        average_completion_tokens=average([run.completion_tokens for run in matching]),
        average_tool_calls=average([run.tool_calls for run in matching]),
        stop_reasons=dict(
            sorted(
                Counter(run.stop_reason for run in matching if not run.end_to_end_success).items()
            )
        ),
        run_counts=counts,
        complete=complete,
    )


def write_locked_evaluation_manifest(
    path: Path,
    summary: LockedEvaluationSummary,
    runs: list[RunMetrics],
) -> None:
    if not summary.complete:
        raise ValueError("an incomplete or duplicated locked evaluation cannot be frozen")
    matching = [
        run
        for run in runs
        if run.agent_version == summary.agent_version and run.case_id in summary.case_ids
    ]
    payload = {
        "schema_version": 1,
        "evaluation_type": "one_shot_locked_split",
        "frozen_at": datetime.now(UTC).isoformat(),
        "summary": asdict(summary),
        "runs": [
            {
                "task_id": run.task_id,
                "case_id": run.case_id,
                "status": run.status,
                "success": run.end_to_end_success,
                "model_calls": run.model_calls,
                "completion_tokens": run.completion_tokens,
                "tool_calls": run.tool_calls,
                "tool_failures": run.tool_failures,
                "deterministic_recoveries": run.deterministic_recoveries,
                "target_test_passed": run.target_test_passed,
                "regression_passed": run.regression_passed,
                "stop_reason": run.stop_reason,
            }
            for run in matching
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
