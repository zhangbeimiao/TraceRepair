"""Print reproducible metrics from historical end-to-end model traces."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tracerepair.evaluation_report import TraceEvaluator


def main() -> None:
    database = ROOT / "data" / "model-agent.sqlite3"
    evaluator = TraceEvaluator(database)
    try:
        runs = evaluator.runs(task_prefix="model-agent-")
        aggregate = evaluator.aggregate(task_prefix="model-agent-")
        print("Historical end-to-end run metrics")
        print(json.dumps(aggregate.to_dict(), ensure_ascii=False, indent=2))
        print("Version cohorts")
        for version in sorted({run.agent_version for run in runs}):
            cohort = evaluator.aggregate(task_prefix="model-agent-", agent_version=version)
            print(
                f"{version}: runs={cohort.runs} successes={cohort.successful_runs} "
                f"success_rate={cohort.success_rate:.2%} "
                f"avg_tokens={cohort.average_completion_tokens}"
            )
        print("Recent runs")
        for run in runs[-10:]:
            print(
                f"{run.task_id} version={run.agent_version} case={run.case_id} status={run.status} "
                f"calls={run.model_calls} tokens={run.completion_tokens} "
                f"tools={run.tool_calls} recoveries={run.deterministic_recoveries} "
                f"target={run.target_test_passed} regression={run.regression_passed}"
            )
    finally:
        evaluator.close()


if __name__ == "__main__":
    main()
