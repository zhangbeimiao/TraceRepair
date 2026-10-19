"""Export frozen metrics and sanitized traces into a dependency-free local Web demo."""

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
from tracerepair.version import AGENT_VERSION, PROJECT_VERSION

DEV_CASES = {"01", "03", "07", "10"}
LOCKED_CASES = {"02", "04", "06", "08", "09"}


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    dev_path = ROOT / "evaluation" / "frozen" / f"devset-v{AGENT_VERSION}.json"
    test_path = ROOT / "evaluation" / "frozen" / f"testset-v{AGENT_VERSION}.json"
    dev = read_json(dev_path)
    test = read_json(test_path)
    if not isinstance(dev, dict) or not isinstance(test, dict):
        raise ValueError("frozen evaluation manifests must be JSON objects")
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
        "agentVersion": AGENT_VERSION,
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
    )
    payload = {
        "generatedAt": generated_at,
        "summary": summary,
        "cohorts": cohorts,
        "traces": traces,
        "failures": failures,
        "recoveryScenarios": recovery_manifest["scenarios"],
        "repositoryCohort": repository_cohort,
    }

    dist = ROOT / "demo" / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "data.js").write_text(
        "window.TRACEREPAIR_DEMO = "
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )
    release_path = ROOT / "evaluation" / "frozen" / f"release-summary-v{AGENT_VERSION}.json"
    release_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": payload["generatedAt"],
                "summary": summary,
                "source_manifests": [
                    dev_path.relative_to(ROOT).as_posix(),
                    test_path.relative_to(ROOT).as_posix(),
                    failure_path.relative_to(ROOT).as_posix(),
                    recovery_path.relative_to(ROOT).as_posix(),
                ]
                + (
                    [repository_path.relative_to(ROOT).as_posix()]
                    if repository_path.is_file()
                    else []
                ),
                "failure_showcase": {
                    "runs": len(failures),
                    "categories": [failure["category"] for failure in failures],
                },
                "recovery_showcase": {
                    "runs": len(recovery_manifest["scenarios"]),
                    "crash_points": [
                        scenario["crash_point"]
                        for scenario in recovery_manifest["scenarios"]
                    ],
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Web demo exported: {dist.relative_to(ROOT)}; "
        f"runs={summary['runs']} successes={summary['successes']} "
        f"bug_types={summary['evaluatedBugTypes']}"
    )


if __name__ == "__main__":
    main()
