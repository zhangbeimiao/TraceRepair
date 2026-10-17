"""Run each locked case once without tuning or retrying failed attempts."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tracerepair.evaluation_report import TraceEvaluator
from tracerepair.locked_evaluation import (
    summarize_locked_evaluation,
    write_locked_evaluation_manifest,
)
from tracerepair.version import AGENT_VERSION

LOCKED_CASES = ("02", "04", "06", "08", "09")
FROZEN_AGENT_VERSION = "0.4.0-dev1"


def load_runs():
    evaluator = TraceEvaluator(ROOT / "data" / "model-agent.sqlite3")
    try:
        return evaluator.runs(task_prefix="model-agent-", agent_version=AGENT_VERSION)
    finally:
        evaluator.close()


def main() -> None:
    if AGENT_VERSION != FROZEN_AGENT_VERSION:
        raise SystemExit(
            f"locked evaluation requires frozen agent {FROZEN_AGENT_VERSION}, got {AGENT_VERSION}"
        )
    if not os.getenv("DASHSCOPE_API_KEY") or not os.getenv("TRACEREPAIR_BAILIAN_BASE_URL"):
        raise SystemExit("Bailian environment variables are not configured in this terminal")

    existing = load_runs()
    counts = {
        case_id: sum(run.case_id == case_id for run in existing) for case_id in LOCKED_CASES
    }
    duplicates = [case_id for case_id, count in counts.items() if count > 1]
    if duplicates:
        raise SystemExit(f"locked evaluation already has duplicate runs: {duplicates}")

    pending = [case_id for case_id, count in counts.items() if count == 0]
    environment = os.environ.copy()
    environment["TEMP"] = str(ROOT / "tmp")
    environment["TMP"] = str(ROOT / "tmp")
    print(
        f"Locked one-shot evaluation for agent {AGENT_VERSION}. "
        f"Pending cases: {pending or 'none'}. Maximum new provider requests: {len(pending) * 4}."
    )
    process_failures = 0
    for index, case_id in enumerate(pending, start=1):
        print(f"\n=== locked run {index}/{len(pending)}; case {case_id} ===")
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "model_repair_agent.py"),
                    "--case",
                    case_id,
                    "--evaluation-split",
                    "locked",
                ],
                cwd=ROOT,
                env=environment,
                check=False,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            process_failures += 1
            print("Run stopped after the 300-second process timeout; it will not be retried blindly.")
            continue
        if completed.returncode != 0:
            process_failures += 1

    runs = load_runs()
    summary = summarize_locked_evaluation(
        runs,
        case_ids=LOCKED_CASES,
        agent_version=AGENT_VERSION,
    )
    print("\n=== locked evaluation result ===")
    print(
        f"runs={summary.runs}/5 successes={summary.successful_runs} "
        f"success_rate={summary.success_rate:.2%} complete={summary.complete}"
    )
    print(
        f"average_calls={summary.average_model_calls} "
        f"average_tokens={summary.average_completion_tokens} "
        f"average_tools={summary.average_tool_calls}"
    )
    print(
        f"run_counts={summary.run_counts} stop_reasons={summary.stop_reasons} "
        f"process_failures={process_failures}"
    )
    if not summary.complete:
        raise SystemExit(
            "Locked evaluation is incomplete. Inspect timed-out/running traces before any further action."
        )

    manifest = ROOT / "evaluation" / "frozen" / f"testset-v{AGENT_VERSION}.json"
    write_locked_evaluation_manifest(manifest, summary, runs)
    print(f"Locked evaluation frozen: {manifest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
