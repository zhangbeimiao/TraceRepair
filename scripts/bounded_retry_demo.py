"""Offline proof that bounded retry does not stack failed patches.

This demo uses two deliberately scripted candidate diffs against EventRelay case
05.  It makes no provider request: the point is to make the controller's retry
and clean-snapshot guarantee reproducible before a model planner is attached.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.materialize import materialize_case
from tracerepair.bounded_retry import BoundedRetryWorkflow, RetryCandidate, retry_metrics
from tracerepair.models import Task, TaskStatus
from tracerepair.store import TraceStore


TARGET = "tests/test_repair_targets.py::test_case_05_parses_false_as_false"
NON_FIXING = """--- a/src/eventrelay/config.py
+++ b/src/eventrelay/config.py
@@ -6,6 +6,7 @@
     if value is None:
         return default
     normalized = value.strip().lower()
+    # First candidate is policy-valid but deliberately insufficient.
     if value:
         return True
"""
FIX = """--- a/src/eventrelay/config.py
+++ b/src/eventrelay/config.py
@@ -6,6 +6,4 @@
     if value is None:
         return default
     normalized = value.strip().lower()
-    if value:
-        return True
     if normalized in {\"1\", \"true\", \"yes\", \"on\"}:
         return True
"""


def main() -> None:
    root = Path("runs") / "bounded-retry-demo-v0.9.0-dev1"
    if root.exists():
        shutil.rmtree(root)
    baseline = materialize_case("05", root / "baseline")
    store = TraceStore(root / "trace.sqlite3")
    task_id = "bounded-retry-demo-case-05"
    store.create_task(Task(task_id, "05", "false must parse as False", str(baseline)))
    store.transition(task_id, TaskStatus.READY, "offline retry demo")
    candidates = [
        RetryCandidate(NON_FIXING, model_calls=0, completion_tokens=0, planner_reason="scripted"),
        RetryCandidate(FIX, model_calls=0, completion_tokens=0, planner_reason="scripted"),
    ]

    def provider(attempt_id: int, _feedback: dict[str, object] | None) -> RetryCandidate:
        return candidates[attempt_id - 1]

    result = BoundedRetryWorkflow(
        task_id,
        store,
        baseline_workspace=baseline,
        attempts_root=root / "attempts",
        target_selector=TARGET,
        candidate_provider=provider,
    ).run()
    state = store.load_checkpoint(task_id)["bounded_retry"]
    summary = {
        "agent_version": "0.9.0-dev1",
        "provider_requests": 0,
        "final_status": result.status,
        "attempt_count": result.attempt_count,
        "rescued_on_second_attempt": result.rescued_on_second_attempt,
        "same_clean_snapshot": state["attempts"][0]["workspace_before_sha256"]
        == state["attempts"][1]["workspace_before_sha256"],
        "metrics": retry_metrics(state),
        "attempts": state["attempts"],
    }
    (root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("Bounded retry demo completed.")
    print("attempt 1: target failure in disposable clean snapshot")
    print("attempt 2: rebuilt from the same snapshot; target and regression passed")
    print(f"Final status: {result.status}; rescued_on_second_attempt={result.rescued_on_second_attempt}")
    print(f"Evidence: {root / 'summary.json'}")
    store.close()


if __name__ == "__main__":
    main()
