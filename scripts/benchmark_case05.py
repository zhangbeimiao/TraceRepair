"""Run bounded case-05 attempts for the currently configured agent version."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tracerepair.benchmark import assess_stability, write_freeze_manifest
from tracerepair.evaluation_report import TraceEvaluator
from tracerepair.version import AGENT_VERSION


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=4, help="additional runs, from 1 to 4")
    arguments = parser.parse_args()
    if not 1 <= arguments.runs <= 4:
        parser.error("--runs must be between 1 and 4")
    if not os.getenv("DASHSCOPE_API_KEY") or not os.getenv("TRACEREPAIR_BAILIAN_BASE_URL"):
        raise SystemExit("Bailian environment variables are not configured in this terminal")

    environment = os.environ.copy()
    environment["TEMP"] = str(ROOT / "tmp")
    environment["TMP"] = str(ROOT / "tmp")
    print(
        f"Starting {arguments.runs} bounded case-05 runs for agent {AGENT_VERSION}. "
        f"Maximum provider requests: {arguments.runs * 4}."
    )
    failed_processes = 0
    for index in range(1, arguments.runs + 1):
        print(f"\n=== benchmark run {index}/{arguments.runs} ===")
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "model_repair_agent.py"),
                    "--case",
                    "05",
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
        decision = assess_stability(
            evaluator,
            case_id="05",
            agent_version=AGENT_VERSION,
            minimum_runs=5,
            required_success_rate=0.8,
        )
        print("\n=== cohort result ===")
        print(
            f"version={decision.agent_version} case={decision.case_id} runs={decision.runs} "
            f"successes={decision.successful_runs} success_rate={decision.success_rate:.2%}"
        )
        print(
            f"average_tokens={decision.average_completion_tokens} "
            f"average_tool_calls={decision.average_tool_calls} "
            f"stop_reasons={decision.stop_reasons} subprocess_failures={failed_processes}"
        )
        if decision.stable:
            manifest = ROOT / "evaluation" / "frozen" / f"case-05-v{AGENT_VERSION}.json"
            write_freeze_manifest(
                manifest,
                decision,
                evaluator.runs(task_prefix="model-agent-", agent_version=AGENT_VERSION, case_id="05"),
            )
            print(f"Case 05 frozen: {manifest.relative_to(ROOT)}")
        else:
            print("Case 05 not frozen: the minimum run count or 80% success threshold was not met.")
    finally:
        evaluator.close()


if __name__ == "__main__":
    main()
