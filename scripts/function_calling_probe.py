"""One low-cost provider probe for the native function-calling contract."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tracerepair.function_calling import NativeFunctionPlanner
from tracerepair.model_planner import BailianChatTransport, PlannerConfig, PlannerError
from tracerepair.models import Task
from tracerepair.store import TraceStore


def main() -> None:
    task_id = f"function-probe-{uuid4().hex[:8]}"
    database = ROOT / "data" / "function-calling-probe.sqlite3"
    store = TraceStore(database)
    try:
        store.create_task(Task(task_id, "probe", "find boolean parser", "D:/probe"))
        planner = NativeFunctionPlanner(
            BailianChatTransport(),
            PlannerConfig(
                max_completion_tokens=128,
                max_calls_per_task=1,
                max_total_completion_tokens=128,
                max_context_chars=2_000,
            ),
        )
        plan = planner.suggest(
            task_id,
            store,
            "A failing test says configuration value false is parsed as true. Choose how to locate "
            "the relevant source without guessing a path.",
            allowed_tools={"repo_map", "search_code"},
            allow_patch=False,
            stage="diagnosis",
        )
        event = store.list_events(task_id)[-1]
        print("Native function-calling probe completed.")
        print(f"Function: {event.payload.get('function_name')}")
        print(f"Plan kind: {plan.kind}")
        print(f"Output tokens: {plan.completion_tokens}/128")
        print(f"Prompt: {event.payload.get('prompt_id')} {event.payload.get('prompt_sha256')}")
        print(f"Tool schema SHA-256: {event.payload.get('tool_schema_sha256')}")
        print(f"Trace database: data/function-calling-probe.sqlite3 (task {task_id})")
    except PlannerError as error:
        print(f"Native function-calling probe stopped safely: {error}")
        raise SystemExit(1) from error
    finally:
        store.close()


if __name__ == "__main__":
    main()
