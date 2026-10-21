"""Export frozen metrics and sanitized traces into a dependency-free local Web demo."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tracerepair.demo_evidence import (
    build_failure_control_summary,
    build_patch_preview,
    build_verification_summary,
)
from tracerepair.evaluation_report import TraceEvaluator
from tracerepair.showcase import load_showcase_trace, showcase_steps
from tracerepair.version import PROJECT_VERSION

DEV_CASES = {"01", "03", "07", "10"}
LOCKED_CASES = {"02", "04", "06", "08", "09"}
CONTROLLED_AGENT_VERSION = "0.4.0-dev1"
HISTORICAL_BENCHMARK_ID = "historical-python-v1.1.3"
FROZEN_HISTORICAL_AGENT_VERSION = "0.6.0"


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    # The EventRelay traces are retained as controlled engineering regression
    # evidence. The headline result is the separately frozen real-history
    # benchmark below; never silently reinterpret the older cohort as v0.5.0.
    dev_path = ROOT / "evaluation" / "frozen" / f"devset-v{CONTROLLED_AGENT_VERSION}.json"
    test_path = ROOT / "evaluation" / "frozen" / f"testset-v{CONTROLLED_AGENT_VERSION}.json"
    dev = read_json(dev_path)
    test = read_json(test_path)
    if not isinstance(dev, dict) or not isinstance(test, dict):
        raise ValueError("frozen evaluation manifests must be JSON objects")
    historical_path = (
        ROOT / "evaluation" / "frozen" / f"{HISTORICAL_BENCHMARK_ID}.json"
    )
    historical_checksum_path = historical_path.with_suffix(".json.sha256")
    historical = read_json(historical_path)
    if not isinstance(historical, dict):
        raise ValueError("historical benchmark summary must be a JSON object")
    expected_historical_sha = historical_checksum_path.read_text(encoding="utf-8").split()[0]
    if sha256_file(historical_path) != expected_historical_sha:
        raise ValueError("historical benchmark summary checksum mismatch")
    if historical.get("release_agent_version") != FROZEN_HISTORICAL_AGENT_VERSION:
        raise ValueError("historical benchmark agent version changed unexpectedly")
    historical_summary = historical.get("summary")
    historical_attempts = historical.get("attempts")
    if not isinstance(historical_summary, dict) or not isinstance(historical_attempts, list):
        raise ValueError("historical benchmark summary is incomplete")
    historical_splits = historical.get("splits")
    if not isinstance(historical_splits, dict):
        raise ValueError("historical benchmark split summary is missing")
    failure_attempts = [attempt for attempt in historical_attempts if not attempt.get("success")]
    historical_benchmark = {
        "benchmarkId": historical.get("benchmark_id"),
        "protocol": historical.get("protocol"),
        "agentVersion": historical.get("release_agent_version"),
        "evaluatedRuntimeAgentVersion": historical.get("evaluated_runtime_agent_version"),
        "model": historical.get("model"),
        "runs": historical_summary.get("attempted_tasks"),
        "successes": historical_summary.get("successes"),
        "failures": historical_summary.get("failures"),
        "passAt1": historical_summary.get("pass_at_1"),
        "humanHandoffs": historical_summary.get("human_handoffs"),
        "incorrectAcceptedPatches": historical_summary.get("incorrect_accepted_patches"),
        "averageTokens": historical_summary.get("average_completion_tokens"),
        "totalTokens": historical_summary.get("total_completion_tokens"),
        "p50Seconds": historical_summary.get("p50_wall_seconds"),
        "p95Seconds": historical_summary.get("p95_wall_seconds"),
        "wilson95": historical_summary.get("wilson_95_percent"),
        "attempts": historical_attempts,
        "splits": historical_splits,
        "failureAttempts": failure_attempts,
        "manifestSha256": historical.get("manifest_sha256"),
        "agentConfigSha256": historical.get("agent_config_sha256"),
        "reportSha256": historical.get("report_sha256"),
        "terminalLedgerSha256": historical.get("terminal_ledger_sha256"),
        "frozenSummarySha256": expected_historical_sha,
        "scopeNote": historical.get("scope_note"),
    }
    catalog_payload = read_json(ROOT / "evaluation" / "cases.json")
    if not isinstance(catalog_payload, list):
        raise ValueError("case catalog must be a JSON array")
    case_by_id = {
        str(case["id"]): case
        for case in catalog_payload
        if isinstance(case, dict)
    }
    catalog = {
        case_id: str(case["name"])
        for case_id, case in case_by_id.items()
    }
    frozen_runs = list(dev["runs"]) + list(test["runs"])
    task_ids = {str(run["task_id"]) for run in frozen_runs}
    failure_path = ROOT / "evaluation" / "frozen" / "failure-showcase-v0.4.0.json"
    failure_manifest = read_json(failure_path)
    if not isinstance(failure_manifest, dict) or not isinstance(
        failure_manifest.get("failures"), list
    ):
        raise ValueError("failure showcase manifest must contain a failures array")
    recovery_path = ROOT / "evaluation" / "frozen" / "recovery-showcase-v0.4.1.json"
    recovery_manifest = read_json(recovery_path)
    if not isinstance(recovery_manifest, dict) or not isinstance(
        recovery_manifest.get("scenarios"), list
    ):
        raise ValueError("recovery showcase manifest must contain a scenarios array")
    repository_path = (
        ROOT
        / "evaluation"
        / "frozen"
        / f"repository-mini-repo-discount-v{PROJECT_VERSION}.json"
    )
    repository_cohort: dict[str, object] | None = None
    if repository_path.is_file():
        repository_manifest = read_json(repository_path)
        if not isinstance(repository_manifest, dict):
            raise ValueError("configured repository manifest must be a JSON object")
        decision = repository_manifest.get("decision")
        metadata = repository_manifest.get("metadata")
        if not isinstance(decision, dict) or not isinstance(metadata, dict):
            raise ValueError("configured repository manifest is missing decision metadata")
        if metadata.get("not_a_locked_generalization_result") is not True:
            raise ValueError("configured repository evidence scope must remain explicit")
        repository_cohort = {
            "projectVersion": metadata.get("project_version"),
            "task": metadata.get("repository_task"),
            "runs": decision.get("runs"),
            "successes": decision.get("successful_runs"),
            "successRate": decision.get("success_rate"),
            "averageTokens": decision.get("average_completion_tokens"),
            "averageToolCalls": decision.get("average_tool_calls"),
            "scope": metadata.get("evidence_scope"),
        }
    locked_repository_path = (
        ROOT / "evaluation" / "frozen" / f"locked-repository-v{PROJECT_VERSION}.json"
    )
    locked_repository_result: dict[str, object] | None = None
    if locked_repository_path.is_file():
        locked_repository_manifest = read_json(locked_repository_path)
        if not isinstance(locked_repository_manifest, dict):
            raise ValueError("locked repository manifest must be a JSON object")
        protocol = locked_repository_manifest.get("protocol")
        locked_run = locked_repository_manifest.get("run")
        if not isinstance(protocol, dict) or not isinstance(locked_run, dict):
            raise ValueError("locked repository manifest is missing protocol or run data")
        if (
            protocol.get("one_shot") is not True
            or protocol.get("retry_on_failure") is not False
            or protocol.get("prompt_or_policy_changes_after_reveal") is not False
            or protocol.get("repository_details_published") is not False
        ):
            raise ValueError("locked repository protocol no longer proves a private one-shot run")
        if protocol.get("project_version") != PROJECT_VERSION:
            raise ValueError("locked repository project version does not match the demo")
        for private_key in ("repository_task", "repository_commit", "config_sha256"):
            if private_key in protocol:
                raise ValueError("locked repository public manifest contains private metadata")
        locked_repository_result = {
            "projectVersion": protocol.get("project_version"),
            "agentVersion": protocol.get("agent_version"),
            "model": protocol.get("model"),
            "scope": protocol.get("evidence_scope"),
            "success": locked_run.get("end_to_end_success"),
            "status": locked_run.get("status"),
            "modelCalls": locked_run.get("model_calls"),
            "tokens": locked_run.get("completion_tokens"),
            "toolCalls": locked_run.get("tool_calls"),
            "targetPassed": locked_run.get("target_test_passed"),
            "regressionPassed": locked_run.get("regression_passed"),
            "oneShot": True,
            "retried": False,
        }

    evaluator = TraceEvaluator(ROOT / "data" / "model-agent.sqlite3")
    try:
        all_runs = evaluator.runs(task_prefix="model-agent-")
        all_run_by_id = {run.task_id: run for run in all_runs}
        run_by_id = {task_id: all_run_by_id[task_id] for task_id in task_ids if task_id in all_run_by_id}
        if set(run_by_id) != task_ids:
            missing = sorted(task_ids - set(run_by_id))
            raise ValueError(f"frozen traces are missing from the database: {missing}")
        cohorts = []
        for version in sorted({run.agent_version for run in all_runs}):
            metrics = evaluator.aggregate(task_prefix="model-agent-", agent_version=version)
            cohorts.append(
                {
                    "version": version,
                    "runs": metrics.runs,
                    "successes": metrics.successful_runs,
                    "successRate": metrics.success_rate,
                    "averageTokens": metrics.average_completion_tokens,
                }
            )
    finally:
        evaluator.close()

    traces = []
    for task_id in sorted(task_ids, key=lambda value: (value[12:14], value)):
        metrics = run_by_id[task_id]
        trace = load_showcase_trace(ROOT / "data" / "model-agent.sqlite3", task_id)
        split = "locked" if metrics.case_id in LOCKED_CASES else "development"
        patch_preview = build_patch_preview(trace, case_by_id[metrics.case_id], ROOT)
        traces.append(
            {
                "taskId": task_id,
                "caseId": metrics.case_id,
                "caseName": catalog[metrics.case_id],
                "split": split,
                "issue": trace.issue,
                "status": metrics.status,
                "success": metrics.end_to_end_success,
                "modelCalls": metrics.model_calls,
                "tokens": metrics.completion_tokens,
                "toolCalls": metrics.tool_calls,
                "toolFailures": metrics.tool_failures,
                "recoveries": metrics.deterministic_recoveries,
                "targetPassed": metrics.target_test_passed,
                "regressionPassed": metrics.regression_passed,
                "timeline": list(showcase_steps(trace)),
                "patchPreview": patch_preview,
                "verification": build_verification_summary(trace),
            }
        )

    failures = []
    for definition in failure_manifest["failures"]:
        if not isinstance(definition, dict):
            raise ValueError("failure showcase entries must be JSON objects")
        task_id = str(definition["task_id"])
        metrics = all_run_by_id.get(task_id)
        if metrics is None:
            raise ValueError(f"frozen failure trace is missing from the database: {task_id}")
        trace = load_showcase_trace(ROOT / "data" / "model-agent.sqlite3", task_id)
        control = build_failure_control_summary(trace)
        if trace.status != definition["expected_status"]:
            raise ValueError(f"frozen failure status changed: {task_id}")
        if control["stopReason"] != definition["expected_stop_reason"]:
            raise ValueError(f"frozen failure stop reason changed: {task_id}")
        failures.append(
            {
                "taskId": task_id,
                "caseId": metrics.case_id,
                "caseName": catalog[metrics.case_id],
                "title": str(definition["title"]),
                "category": str(definition["category"]),
                "issue": trace.issue,
                "status": trace.status,
                "agentVersion": metrics.agent_version,
                "modelCalls": metrics.model_calls,
                "tokens": metrics.completion_tokens,
                "toolCalls": metrics.tool_calls,
                "control": control,
                "controlOutcome": str(definition["control_outcome"]),
                "lesson": str(definition["lesson"]),
                "timeline": list(showcase_steps(trace)),
            }
        )

    total_runs = len(traces)
    total_tokens = sum(int(trace["tokens"]) for trace in traces)
    total_tools = sum(int(trace["toolCalls"]) for trace in traces)
    summary = {
        "agentVersion": FROZEN_HISTORICAL_AGENT_VERSION,
        "controlledAgentVersion": CONTROLLED_AGENT_VERSION,
        "evaluatedBugTypes": len(DEV_CASES | LOCKED_CASES),
        "runs": total_runs,
        "successes": sum(bool(trace["success"]) for trace in traces),
        "successRate": round(sum(bool(trace["success"]) for trace in traces) / total_runs, 4),
        "averageTokens": round(total_tokens / total_runs, 2),
        "averageToolCalls": round(total_tools / total_runs, 2),
        "development": dev["decision"],
        "locked": test["summary"],
    }
    generated_at = max(
        str(dev["frozen_at"]),
        str(test["frozen_at"]),
        str(failure_manifest["frozen_at"]),
        str(recovery_manifest["frozen_at"]),
        str(repository_manifest["frozen_at"])
        if repository_path.is_file()
        else "",
        str(locked_repository_manifest["frozen_at"])
        if locked_repository_path.is_file()
        else "",
    )
    payload = {
        "generatedAt": generated_at,
        "summary": summary,
        "cohorts": cohorts,
        "traces": traces,
        "failures": failures,
        "recoveryScenarios": recovery_manifest["scenarios"],
        "historicalBenchmark": historical_benchmark,
        "repositoryCohort": repository_cohort,
        "lockedRepositoryResult": locked_repository_result,
    }

    dist = ROOT / "demo" / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "data.js").write_text(
        "window.TRACEREPAIR_DEMO = "
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )
    print(
        f"Web demo exported: {dist.relative_to(ROOT)}; "
        f"runs={summary['runs']} successes={summary['successes']} "
        f"bug_types={summary['evaluatedBugTypes']}"
    )


if __name__ == "__main__":
    main()
