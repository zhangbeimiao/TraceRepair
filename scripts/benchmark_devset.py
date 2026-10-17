"""Run a bounded repeat benchmark for the generalized development cases."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tracerepair.benchmark import assess_suite_stability, write_suite_freeze_manifest
from tracerepair.evaluation_report import TraceEvaluator
from tracerepair.version import AGENT_VERSION

DEV_CASES = ("01", "03", "07", "10")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="additional runs per case, from 1 to 2",
    )
    arguments = parser.parse_args()
    if not 1 <= arguments.repeats <= 2:
        parser.error("--repeats must be between 1 and 2")
    if not os.getenv("DASHSCOPE_API_KEY") or not os.getenv("TRACEREPAIR_BAILIAN_BASE_URL"):
        raise SystemExit("Bailian environment variables are not configured in this terminal")

    environment = os.environ.copy()
    environment["TEMP"] = str(ROOT / "tmp")
    environment["TMP"] = str(ROOT / "tmp")
    total_runs = arguments.repeats * len(DEV_CASES)
    print(
        f"Starting {total_runs} bounded development-set runs for agent {AGENT_VERSION}. "
        f"Maximum provider requests: {total_runs * 4}."
    )
    failed_processes = 0
    run_index = 0
    for _ in range(arguments.repeats):
        for case_id in DEV_CASES:
            run_index += 1
            print(f"\n=== benchmark run {run_index}/{total_runs}; case {case_id} ===")
            try:
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "model_repair_agent.py"),
                        "--case",
                        case_id,
                    ],
                    cwd=ROOT,
                    env=environment,
                    check=False,
                    timeout=300,
                )
            except subprocess.TimeoutExpired:
                failed_processes += 1
                print("Run stopped after the 300-second process timeout.")
                continue
            if completed.returncode != 0:
                failed_processes += 1

    evaluator = TraceEvaluator(ROOT / "data" / "model-agent.sqlite3")
    try:
        decision = assess_suite_stability(
            evaluator,
            case_ids=DEV_CASES,
            agent_version=AGENT_VERSION,
            minimum_runs_per_case=2,
            required_success_rate=0.8,
            required_case_success_rate=0.5,
        )
        print("\n=== development-set result ===")
        print(
            f"version={decision.agent_version} runs={decision.runs} "
            f"successes={decision.successful_runs} success_rate={decision.success_rate:.2%}"
        )
        print(
            f"average_tokens={decision.average_completion_tokens} "
            f"average_tool_calls={decision.average_tool_calls} "
            f"stop_reasons={decision.stop_reasons} subprocess_failures={failed_processes}"
        )
        for case in decision.cases:
            print(
                f"case={case.case_id} runs={case.runs} successes={case.successful_runs} "
                f"success_rate={case.success_rate:.2%}"
            )
        if decision.stable:
            manifest = ROOT / "evaluation" / "frozen" / f"devset-v{AGENT_VERSION}.json"
            write_suite_freeze_manifest(
                manifest,
                decision,
                evaluator.runs(task_prefix="model-agent-", agent_version=AGENT_VERSION),
            )
            print(f"Development set frozen: {manifest.relative_to(ROOT)}")
        else:
            print(
                "Development set not frozen: each case needs two runs, each case must reach "
                "50%, and the combined success rate must reach 80%."
            )
    finally:
        evaluator.close()


if __name__ == "__main__":
    main()
