from pathlib import Path

from tracerepair.evaluation_report import TraceEvaluator
from tracerepair.models import Task, TaskStatus
from tracerepair.store import TraceStore


def _model_plan(store: TraceStore, task_id: str, tokens: int, accepted: bool = True) -> None:
    store.append_event(
        task_id,
        "model_plan_recorded",
        {
            "kind": "patch" if accepted else "invalid",
            "tool": None,
            "completion_tokens": tokens,
            "policy_accepted": accepted,
        },
    )


def _tool(store: TraceStore, task_id: str, name: str, ok: bool) -> None:
    store.append_event(
        task_id,
        "tool_finished",
        {"call_id": f"{task_id}-{name}", "tool": name, "ok": ok, "error_code": None},
    )


def make_metrics_database(tmp_path: Path) -> Path:
    path = tmp_path / "metrics.sqlite3"
    store = TraceStore(path)
    store.create_task(Task("model-agent-success", "05", "issue", "D:/success"))
    store.append_event(
        "model-agent-success", "run_metadata", {"agent_version": "0.3.0", "model": "fake"}
    )
    store.transition("model-agent-success", TaskStatus.READY, "ready")
    store.transition("model-agent-success", TaskStatus.RUNNING, "run")
    _model_plan(store, "model-agent-success", 40)
    _model_plan(store, "model-agent-success", 160)
    store.append_event(
        "model-agent-success", "deterministic_recovery", {"action": "read_file"}
    )
    _tool(store, "model-agent-success", "run_tests", True)
    _tool(store, "model-agent-success", "run_regression", True)
    store.transition("model-agent-success", TaskStatus.AWAITING_REVIEW, "verified")

    store.create_task(Task("model-agent-stopped", "05", "issue", "D:/stopped"))
    store.transition("model-agent-stopped", TaskStatus.READY, "ready")
    store.transition("model-agent-stopped", TaskStatus.RUNNING, "run")
    _model_plan(store, "model-agent-stopped", 50, accepted=False)
    _tool(store, "model-agent-stopped", "read_file", False)
    store.transition("model-agent-stopped", TaskStatus.NEEDS_HUMAN, "safe stop")
    store.close()
    return path


def test_run_metrics_derive_verification_and_safety_data(tmp_path: Path) -> None:
    evaluator = TraceEvaluator(make_metrics_database(tmp_path))

    runs = evaluator.runs(task_prefix="model-agent-")

    assert runs[0].end_to_end_success is True
    assert runs[0].agent_version == "0.3.0"
    assert runs[0].completion_tokens == 200
    assert runs[0].deterministic_recoveries == 1
    assert runs[1].end_to_end_success is False
    assert runs[1].agent_version == "legacy"
    assert runs[1].model_policy_rejections == 1
    assert runs[1].tool_failures == 1
    evaluator.close()


def test_aggregate_metrics_report_rates_and_averages(tmp_path: Path) -> None:
    evaluator = TraceEvaluator(make_metrics_database(tmp_path))

    metrics = evaluator.aggregate(task_prefix="model-agent-")

    assert metrics.runs == 2
    assert metrics.successful_runs == 1
    assert metrics.success_rate == 0.5
    assert metrics.average_model_calls == 1.5
    assert metrics.average_completion_tokens == 125.0
    assert metrics.average_tool_calls == 1.5
    assert metrics.total_tool_calls == 3
    assert metrics.tool_failure_rate == 0.3333
    assert metrics.stop_reasons == {"safe stop": 1}
    current = evaluator.aggregate(task_prefix="model-agent-", agent_version="0.3.0")
    assert current.runs == 1
    assert current.success_rate == 1.0
    evaluator.close()
