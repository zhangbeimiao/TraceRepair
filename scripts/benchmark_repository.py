"""Fill and freeze a bounded stability cohort for one configured repository task."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tracerepair.benchmark import assess_stability, write_freeze_manifest
from tracerepair.evaluation_report import TraceEvaluator
from tracerepair.repository_task import RepositoryTaskSpec
from tracerepair.version import AGENT_VERSION, MODEL_ID, PROJECT_VERSION


DEFAULT_TASK = ROOT / "examples" / "tasks" / "mini-repo.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=Path, default=DEFAULT_TASK)
    parser.add_argument(
        "--target-runs",
        type=int,
        default=5,
        help="desired total cohort size, from 1 to 10",
    )
    parser.add_argument(
        "--max-new-runs",
        type=int,
        default=4,
        help="maximum provider-backed runs started by this command, from 0 to 5",
    )
    arguments = parser.parse_args()
    if not 1 <= arguments.target_runs <= 10:
        parser.error("--target-runs must be between 1 and 10")
    if not 0 <= arguments.max_new_runs <= 5:
        parser.error("--max-new-runs must be between 0 and 5")

    spec = RepositoryTaskSpec.load(arguments.task)
    case_id = f"repo-{spec.name}"
    database = ROOT / "data" / "model-agent.sqlite3"
    existing = _matching_runs(database, case_id)
    pending = min(max(0, arguments.target_runs - len(existing)), arguments.max_new_runs)
    print(
        f"Configured repository cohort: task={spec.name} agent={AGENT_VERSION} "
        f"existing={len(existing)} target={arguments.target_runs} pending={pending}."
    )
    if pending and (
        not os.getenv("DASHSCOPE_API_KEY")
        or not os.getenv("TRACEREPAIR_BAILIAN_BASE_URL")
    ):
        raise SystemExit(
            "Bailian environment variables are not configured in this terminal. "
            f"No provider request was made; {pending} run(s) are still pending."
        )

    environment = os.environ.copy()
    environment["TEMP"] = str(ROOT / "tmp")
    environment["TMP"] = str(ROOT / "tmp")
    environment["PYTHONPYCACHEPREFIX"] = str(ROOT / ".cache" / "pycache")
    failed_processes = 0
    if pending:
        print(f"Maximum provider requests for this command: {pending * 4}.")
    for index in range(1, pending + 1):
        print(f"\n=== configured repository run {index}/{pending} ===")
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "model_repair_agent.py"),
                    "--task",
                    str(arguments.task.resolve()),
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

    evaluator = TraceEvaluator(database)
    try:
        decision = assess_stability(
            evaluator,
            case_id=case_id,
            agent_version=AGENT_VERSION,
            minimum_runs=arguments.target_runs,
            required_success_rate=0.8,
        )
        runs = evaluator.runs(
            task_prefix="model-agent-repo-",
            agent_version=AGENT_VERSION,
            case_id=case_id,
        )
        print("\n=== configured repository result ===")
        print(
            f"project={PROJECT_VERSION} agent={decision.agent_version} case={case_id} "
            f"runs={decision.runs} successes={decision.successful_runs} "
            f"success_rate={decision.success_rate:.2%}"
        )
        print(
            f"average_tokens={decision.average_completion_tokens} "
            f"average_tool_calls={decision.average_tool_calls} "
            f"stop_reasons={decision.stop_reasons} subprocess_failures={failed_processes}"
        )
        if decision.stable:
            manifest = (
                ROOT
                / "evaluation"
                / "frozen"
                / f"repository-{spec.name}-v{PROJECT_VERSION}.json"
            )
            write_freeze_manifest(
                manifest,
                decision,
                runs,
                metadata={
                    "project_version": PROJECT_VERSION,
                    "model": MODEL_ID,
                    "repository_task": spec.name,
                    "task_config": _safe_config_label(arguments.task),
                    "evidence_scope": "repeat stability on a public configured repository",
                    "not_a_locked_generalization_result": True,
                },
            )
            print(f"Configured repository cohort frozen: {manifest.relative_to(ROOT)}")
        else:
            missing = max(0, arguments.target_runs - decision.runs)
            print(
                "Cohort not frozen: it requires at least "
                f"{arguments.target_runs} runs, 80% success, and currently needs {missing} more run(s)."
            )
    finally:
        evaluator.close()


def _matching_runs(database: Path, case_id: str) -> list[object]:
    if not database.is_file():
        return []
    evaluator = TraceEvaluator(database)
    try:
        return list(
            evaluator.runs(
                task_prefix="model-agent-repo-",
                agent_version=AGENT_VERSION,
                case_id=case_id,
            )
        )
    finally:
        evaluator.close()


def _safe_config_label(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return f"<external>/{resolved.name}"


if __name__ == "__main__":
    main()
