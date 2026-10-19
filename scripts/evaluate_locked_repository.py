"""Run one configured repository exactly once and freeze success or failure."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tracerepair.evaluation_report import RunMetrics, TraceEvaluator
from tracerepair.repository_task import RepositoryTaskSpec
from tracerepair.version import AGENT_VERSION, MODEL_ID, PROJECT_VERSION


DEFAULT_TASK = ROOT / "data" / "locked-repository-task.json"
ATTEMPT_MARKER = ROOT / "data" / "locked-repository-attempt.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=Path, default=DEFAULT_TASK)
    arguments = parser.parse_args()
    spec = RepositoryTaskSpec.load(arguments.task)
    case_id = f"repo-{spec.name}"
    database = ROOT / "data" / "model-agent.sqlite3"
    existing = _runs(database, case_id)
    if len(existing) > 1:
        raise SystemExit("Locked repository invariant violated: more than one run already exists")

    commit = _clean_repository_commit(spec.repository_root)
    config_sha256 = hashlib.sha256(arguments.task.read_bytes()).hexdigest()
    if not existing:
        if ATTEMPT_MARKER.is_file():
            raise SystemExit(
                "Locked repository was already attempted but produced no persisted run; "
                "a second provider attempt is denied"
            )
        if not os.getenv("DASHSCOPE_API_KEY") or not os.getenv(
            "TRACEREPAIR_BAILIAN_BASE_URL"
        ):
            raise SystemExit(
                "Bailian environment variables are not configured in this terminal. "
                "No provider request was made and the one-shot remains unused."
            )
        print(
            f"Starting one locked repository run for agent {AGENT_VERSION}. "
            "Maximum provider requests: 4. This case will not be retried."
        )
        write_attempt_marker(
            ATTEMPT_MARKER,
            repository_task=spec.name,
            repository_commit=commit,
            config_sha256=config_sha256,
        )
        environment = os.environ.copy()
        environment["TEMP"] = str(ROOT / "tmp")
        environment["TMP"] = str(ROOT / "tmp")
        environment["PYTHONPYCACHEPREFIX"] = str(ROOT / ".cache" / "pycache")
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
            completed = None
            print("Locked run process timed out after 300 seconds; persisted trace will be frozen.")
        if completed is not None and completed.returncode != 0:
            print(f"Locked run process exited with code {completed.returncode}; result will not be retried.")
        existing = _runs(database, case_id)

    if len(existing) != 1:
        raise SystemExit(
            "Locked run did not produce exactly one persisted task; inspect the terminal before retrying."
        )
    run = existing[0]
    manifest = ROOT / "evaluation" / "frozen" / f"locked-repository-v{PROJECT_VERSION}.json"
    write_locked_manifest(
        manifest,
        run,
        repository_task=spec.name,
        repository_commit=commit,
        config_sha256=config_sha256,
    )
    print("\n=== locked repository one-shot result ===")
    print(
        f"project={PROJECT_VERSION} agent={run.agent_version} model={MODEL_ID} "
        f"success={run.end_to_end_success} status={run.status}"
    )
    print(
        f"calls={run.model_calls} tokens={run.completion_tokens} tools={run.tool_calls} "
        f"target={run.target_test_passed} regression={run.regression_passed}"
    )
    print(f"stop_reason={run.stop_reason}")
    print(f"Locked result frozen without retry: {manifest.relative_to(ROOT)}")


def write_attempt_marker(
    path: Path,
    *,
    repository_task: str,
    repository_commit: str,
    config_sha256: str,
) -> None:
    """Persist intent before the provider call so a crash cannot enable a retry."""

    payload = {
        "started_at": datetime.now(UTC).isoformat(),
        "project_version": PROJECT_VERSION,
        "agent_version": AGENT_VERSION,
        "model": MODEL_ID,
        "repository_task": repository_task,
        "repository_commit": repository_commit,
        "config_sha256": config_sha256,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_locked_manifest(
    path: Path,
    run: RunMetrics,
    *,
    repository_task: str,
    repository_commit: str,
    config_sha256: str,
) -> None:
    payload = {
        "schema_version": 1,
        "frozen_at": datetime.now(UTC).isoformat(),
        "protocol": {
            "one_shot": True,
            "retry_on_failure": False,
            "prompt_or_policy_changes_after_reveal": False,
            "project_version": PROJECT_VERSION,
            "agent_version": AGENT_VERSION,
            "model": MODEL_ID,
            "repository_task": repository_task,
            "repository_commit": repository_commit,
            "config_sha256": config_sha256,
        },
        "run": asdict(run),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _runs(database: Path, case_id: str) -> list[RunMetrics]:
    if not database.is_file():
        return []
    evaluator = TraceEvaluator(database)
    try:
        return evaluator.runs(task_prefix="model-agent-repo-", case_id=case_id)
    finally:
        evaluator.close()


def _clean_repository_commit(repository: Path) -> str:
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repository,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=15,
        )
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise SystemExit("Locked repository must be a committed local Git snapshot") from error
    if status.stdout.strip():
        raise SystemExit("Locked repository has uncommitted changes; one-shot evaluation denied")
    commit = head.stdout.strip()
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise SystemExit("Locked repository commit hash is invalid")
    return commit


if __name__ == "__main__":
    main()
