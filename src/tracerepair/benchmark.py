"""Stability decisions and frozen benchmark manifests for one case/version cohort."""

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from tracerepair.evaluation_report import RunMetrics, TraceEvaluator


@dataclass(frozen=True)
class StabilityDecision:
    case_id: str
    agent_version: str
    runs: int
    successful_runs: int
    success_rate: float
    average_completion_tokens: float
    average_tool_calls: float
    stop_reasons: dict[str, int]
    minimum_runs: int
    required_success_rate: float
    stable: bool


@dataclass(frozen=True)
class SuiteStabilityDecision:
    case_ids: tuple[str, ...]
    agent_version: str
    runs: int
    successful_runs: int
    success_rate: float
    average_completion_tokens: float
    average_tool_calls: float
    stop_reasons: dict[str, int]
    minimum_runs_per_case: int
    required_success_rate: float
    required_case_success_rate: float
    cases: tuple[StabilityDecision, ...]
    stable: bool


def assess_stability(
    evaluator: TraceEvaluator,
    *,
    case_id: str,
    agent_version: str,
    minimum_runs: int = 5,
    required_success_rate: float = 0.8,
) -> StabilityDecision:
    if minimum_runs < 1:
        raise ValueError("minimum_runs must be positive")
    if not 0 < required_success_rate <= 1:
        raise ValueError("required_success_rate must be in (0, 1]")
    metrics = evaluator.aggregate(
        task_prefix="model-agent-",
        agent_version=agent_version,
        case_id=case_id,
    )
    stable = metrics.runs >= minimum_runs and metrics.success_rate >= required_success_rate
    return StabilityDecision(
        case_id=case_id,
        agent_version=agent_version,
        runs=metrics.runs,
        successful_runs=metrics.successful_runs,
        success_rate=metrics.success_rate,
        average_completion_tokens=metrics.average_completion_tokens,
        average_tool_calls=metrics.average_tool_calls,
        stop_reasons=metrics.stop_reasons,
        minimum_runs=minimum_runs,
        required_success_rate=required_success_rate,
        stable=stable,
    )


def write_freeze_manifest(
    path: Path, decision: StabilityDecision, runs: list[RunMetrics]
) -> None:
    if not decision.stable:
        raise ValueError("an unstable cohort cannot be frozen")
    matching = [
        run
        for run in runs
        if run.case_id == decision.case_id and run.agent_version == decision.agent_version
    ]
    payload = {
        "schema_version": 1,
        "frozen_at": datetime.now(UTC).isoformat(),
        "decision": asdict(decision),
        "runs": [
            {
                "task_id": run.task_id,
                "status": run.status,
                "success": run.end_to_end_success,
                "model_calls": run.model_calls,
                "completion_tokens": run.completion_tokens,
                "tool_calls": run.tool_calls,
                "deterministic_recoveries": run.deterministic_recoveries,
                "stop_reason": run.stop_reason,
            }
            for run in matching
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def assess_suite_stability(
    evaluator: TraceEvaluator,
    *,
    case_ids: tuple[str, ...],
    agent_version: str,
    minimum_runs_per_case: int = 2,
    required_success_rate: float = 0.8,
    required_case_success_rate: float = 0.5,
) -> SuiteStabilityDecision:
    if not case_ids or len(set(case_ids)) != len(case_ids):
        raise ValueError("case_ids must be non-empty and unique")
    if minimum_runs_per_case < 1:
        raise ValueError("minimum_runs_per_case must be positive")
    if not 0 < required_success_rate <= 1:
        raise ValueError("required_success_rate must be in (0, 1]")
    if not 0 < required_case_success_rate <= 1:
        raise ValueError("required_case_success_rate must be in (0, 1]")

    cases = tuple(
        assess_stability(
            evaluator,
            case_id=case_id,
            agent_version=agent_version,
            minimum_runs=minimum_runs_per_case,
            required_success_rate=required_case_success_rate,
        )
        for case_id in case_ids
    )
    runs = [
        run
        for case_id in case_ids
        for run in evaluator.runs(
            task_prefix="model-agent-",
            agent_version=agent_version,
            case_id=case_id,
        )
    ]
    run_count = len(runs)
    successful_runs = sum(run.end_to_end_success for run in runs)
    success_rate = round(successful_runs / run_count, 4) if run_count else 0.0
    average_tokens = (
        round(sum(run.completion_tokens for run in runs) / run_count, 2) if run_count else 0.0
    )
    average_tools = round(sum(run.tool_calls for run in runs) / run_count, 2) if run_count else 0.0
    stop_reasons = dict(
        sorted(Counter(run.stop_reason for run in runs if not run.end_to_end_success).items())
    )
    stable = all(case.stable for case in cases) and success_rate >= required_success_rate
    return SuiteStabilityDecision(
        case_ids=case_ids,
        agent_version=agent_version,
        runs=run_count,
        successful_runs=successful_runs,
        success_rate=success_rate,
        average_completion_tokens=average_tokens,
        average_tool_calls=average_tools,
        stop_reasons=stop_reasons,
        minimum_runs_per_case=minimum_runs_per_case,
        required_success_rate=required_success_rate,
        required_case_success_rate=required_case_success_rate,
        cases=cases,
        stable=stable,
    )


def write_suite_freeze_manifest(
    path: Path,
    decision: SuiteStabilityDecision,
    runs: list[RunMetrics],
) -> None:
    if not decision.stable:
        raise ValueError("an unstable suite cannot be frozen")
    matching = [
        run
        for run in runs
        if run.case_id in decision.case_ids and run.agent_version == decision.agent_version
    ]
    payload = {
        "schema_version": 1,
        "frozen_at": datetime.now(UTC).isoformat(),
        "decision": asdict(decision),
        "runs": [
            {
                "task_id": run.task_id,
                "case_id": run.case_id,
                "status": run.status,
                "success": run.end_to_end_success,
                "model_calls": run.model_calls,
                "completion_tokens": run.completion_tokens,
                "tool_calls": run.tool_calls,
                "deterministic_recoveries": run.deterministic_recoveries,
                "stop_reason": run.stop_reason,
            }
            for run in matching
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
