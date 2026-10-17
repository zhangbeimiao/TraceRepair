"""Read-only metrics derived from persisted TraceRepair task traces."""

import json
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunMetrics:
    task_id: str
    case_id: str
    agent_version: str
    status: str
    model_calls: int
    completion_tokens: int
    tool_calls: int
    tool_failures: int
    model_policy_rejections: int
    deterministic_recoveries: int
    target_test_passed: bool
    regression_passed: bool
    end_to_end_success: bool
    stop_reason: str


@dataclass(frozen=True)
class AggregateMetrics:
    runs: int
    successful_runs: int
    needs_human_runs: int
    success_rate: float
    average_model_calls: float
    average_completion_tokens: float
    average_tool_calls: float
    total_tool_calls: int
    total_tool_failures: int
    tool_failure_rate: float
    model_policy_rejections: int
    deterministic_recoveries: int
    stop_reasons: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class TraceEvaluator:
    """Aggregate safe metadata without changing the trace database."""

    def __init__(self, database: Path) -> None:
        if not database.is_file():
            raise FileNotFoundError(database)
        self._connection = sqlite3.connect(database)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA query_only = ON")

    def close(self) -> None:
        self._connection.close()

    def runs(
        self,
        *,
        task_prefix: str | None = None,
        agent_version: str | None = None,
        case_id: str | None = None,
    ) -> list[RunMetrics]:
        query = "SELECT task_id, case_id, status FROM tasks"
        parameters: tuple[str, ...] = ()
        if task_prefix is not None:
            query += " WHERE task_id LIKE ?"
            parameters = (f"{task_prefix}%",)
        query += " ORDER BY created_at"
        tasks = self._connection.execute(query, parameters).fetchall()
        runs = [self._run_metrics(row) for row in tasks]
        if agent_version is not None:
            runs = [run for run in runs if run.agent_version == agent_version]
        if case_id is not None:
            runs = [run for run in runs if run.case_id == case_id]
        return runs

    def aggregate(
        self,
        *,
        task_prefix: str | None = None,
        agent_version: str | None = None,
        case_id: str | None = None,
    ) -> AggregateMetrics:
        runs = self.runs(
            task_prefix=task_prefix,
            agent_version=agent_version,
            case_id=case_id,
        )
        count = len(runs)
        successes = sum(run.end_to_end_success for run in runs)
        needs_human = sum(run.status == "needs_human" for run in runs)
        tool_calls = sum(run.tool_calls for run in runs)
        tool_failures = sum(run.tool_failures for run in runs)
        return AggregateMetrics(
            runs=count,
            successful_runs=successes,
            needs_human_runs=needs_human,
            success_rate=_ratio(successes, count),
            average_model_calls=_average([run.model_calls for run in runs]),
            average_completion_tokens=_average([run.completion_tokens for run in runs]),
            average_tool_calls=_average([run.tool_calls for run in runs]),
            total_tool_calls=tool_calls,
            total_tool_failures=tool_failures,
            tool_failure_rate=_ratio(tool_failures, tool_calls),
            model_policy_rejections=sum(run.model_policy_rejections for run in runs),
            deterministic_recoveries=sum(run.deterministic_recoveries for run in runs),
            stop_reasons=dict(
                sorted(Counter(run.stop_reason for run in runs if not run.end_to_end_success).items())
            ),
        )

    def _run_metrics(self, task: sqlite3.Row) -> RunMetrics:
        rows = self._connection.execute(
            "SELECT event_type, payload_json FROM trace_events WHERE task_id = ? ORDER BY sequence",
            (task["task_id"],),
        ).fetchall()
        events = [(row["event_type"], json.loads(row["payload_json"])) for row in rows]
        plans = [payload for kind, payload in events if kind == "model_plan_recorded"]
        tools = [payload for kind, payload in events if kind == "tool_finished"]
        metadata = next(
            (payload for kind, payload in events if kind == "run_metadata"),
            {},
        )
        target_passed = any(
            payload.get("tool") == "run_tests" and payload.get("ok") is True for payload in tools
        )
        regression_passed = any(
            payload.get("tool") == "run_regression" and payload.get("ok") is True
            for payload in tools
        )
        status = str(task["status"])
        status_changes = [payload for kind, payload in events if kind == "status_changed"]
        stop_reason = str(status_changes[-1].get("reason", "unknown")) if status_changes else "unknown"
        return RunMetrics(
            task_id=str(task["task_id"]),
            case_id=str(task["case_id"]),
            agent_version=str(metadata.get("agent_version", "legacy")),
            status=status,
            model_calls=len(plans),
            completion_tokens=sum(int(plan.get("completion_tokens", 0)) for plan in plans),
            tool_calls=len(tools),
            tool_failures=sum(payload.get("ok") is not True for payload in tools),
            model_policy_rejections=sum(plan.get("policy_accepted") is False for plan in plans),
            deterministic_recoveries=sum(kind == "deterministic_recovery" for kind, _ in events),
            target_test_passed=target_passed,
            regression_passed=regression_passed,
            end_to_end_success=status in {"awaiting_review", "succeeded"} and regression_passed,
            stop_reason=stop_reason,
        )


def _average(values: list[int]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0
