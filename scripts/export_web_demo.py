"""Export frozen metrics and sanitized traces into a dependency-free local Web demo."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tracerepair.evaluation_report import TraceEvaluator
from tracerepair.showcase import load_showcase_trace, showcase_steps
from tracerepair.version import AGENT_VERSION

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
    catalog = {
        str(case["id"]): str(case["name"])
        for case in catalog_payload
        if isinstance(case, dict)
    }
    frozen_runs = list(dev["runs"]) + list(test["runs"])
    task_ids = {str(run["task_id"]) for run in frozen_runs}

    evaluator = TraceEvaluator(ROOT / "data" / "model-agent.sqlite3")
    try:
        all_runs = evaluator.runs(task_prefix="model-agent-")
        run_by_id = {run.task_id: run for run in all_runs if run.task_id in task_ids}
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
    generated_at = max(str(dev["frozen_at"]), str(test["frozen_at"]))
    payload = {
        "generatedAt": generated_at,
        "summary": summary,
        "cohorts": cohorts,
        "traces": traces,
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
                ],
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
