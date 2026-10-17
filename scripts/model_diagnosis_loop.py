"""Three-step, read-only live diagnosis with a 288-token output budget."""

import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.materialize import materialize_case
from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.model_planner import BailianChatTransport, ModelPlanner, PlannerConfig, PlannerError
from tracerepair.models import Task, TaskStatus
from tracerepair.read_tools import FileSlice, ReadOnlyRepository, ReadOnlyResult
from tracerepair.store import TraceStore
from tracerepair.test_runner import RestrictedTestRunner


READ_ONLY = {"repo_map", "search_code", "read_file"}


def main() -> None:
    run_id = uuid4().hex[:8]
    workspace = materialize_case("05", ROOT / "workspaces" / "model-diagnosis" / f"case-05-{run_id}")
    store = TraceStore(ROOT / "data" / "model-diagnosis.sqlite3")
    task_id = f"model-diagnosis-{run_id}"
    store.create_task(Task(task_id, "05", "false configuration is interpreted as true", str(workspace)))
    store.transition(task_id, TaskStatus.READY, "diagnosis workspace created")
    store.transition(task_id, TaskStatus.RUNNING, "read-only diagnosis started")
    tools = InstrumentedTools(task_id, store, ReadOnlyRepository(workspace), RestrictedTestRunner(workspace))
    planner = ModelPlanner(BailianChatTransport(), PlannerConfig(max_completion_tokens=96, max_calls_per_task=3, max_total_completion_tokens=288))
    evidence = ("Task: EventRelay case 05. Config value 'false' must parse as False. "
                "Diagnose before repair. Search for distinctive source-code identifiers or literals, "
                "not the task title or case number. Choose one action only. "
                "Never guess a file path: read_file paths must come from repo_map or search results. "
                "Never request patches or tests in this read-only phase.")
    total_tokens = 0
    empty_searches = 0
    seen_actions: set[str] = set()
    try:
        allowed_tools = {"repo_map", "search_code"}
        for turn in range(1, 4):
            plan = planner.suggest(
                task_id, store, evidence, allowed_tools=allowed_tools, allow_patch=False
            )
            total_tokens += plan.completion_tokens
            if plan.kind != "tool" or plan.tool not in READ_ONLY:
                store.transition(task_id, TaskStatus.NEEDS_HUMAN, "model requested action outside read-only diagnosis")
                print(f"Stopped safely at turn {turn}: model selected {plan.kind}:{plan.tool}.")
                break
            action_key = f"{plan.tool}:{json.dumps(plan.arguments, ensure_ascii=False, sort_keys=True)}"
            if action_key in seen_actions:
                store.transition(task_id, TaskStatus.NEEDS_HUMAN, "model repeated the same tool action")
                print(f"Stopped safely at turn {turn}: repeated action was not executed.")
                break
            seen_actions.add(action_key)
            result = execute(tools, plan.tool, plan.arguments)
            summary = summarize(result)
            print(f"Turn {turn}: {plan.tool}; ok={result.ok}; output_tokens={plan.completion_tokens}")
            if not result.ok:
                store.transition(task_id, TaskStatus.NEEDS_HUMAN, "read-only tool failed")
                break
            transition_tool = plan.tool
            if plan.tool == "search_code" and not result.data:
                empty_searches += 1
                if empty_searches >= 2:
                    fallback = tools.repo_map()
                    print(f"Deterministic fallback: repo_map; ok={fallback.ok}; output_tokens=0")
                    summary = "two literal searches returned no matches; repo map fallback: " + summarize(fallback)
                    result = fallback
                    transition_tool = "repo_map"
            allowed_tools = _next_allowed_tools(transition_tool, result)
            evidence = ("Original task: config value 'false' must parse as False. "
                        f"Previous action: {plan.tool} with arguments "
                        f"{json.dumps(plan.arguments, ensure_ascii=False)}. Observation: {summary}. "
                        "Choose one next read-only action: repo_map, search_code, or read_file. "
                        "If there were no matches, search again using a different code identifier or literal. "
                        "Only use read_file with an exact path present in the observation. "
                        "If evidence is sufficient, return handoff.")
        else:
            store.transition(task_id, TaskStatus.NEEDS_HUMAN, "read-only diagnosis budget complete")
        print(f"Diagnosis finished. Output tokens: {total_tokens}/288")
        print(f"Trace database: data/model-diagnosis.sqlite3 (task {task_id})")
    except PlannerError as error:
        if store.get_task(task_id).status is TaskStatus.RUNNING:
            store.transition(task_id, TaskStatus.NEEDS_HUMAN, f"planner stopped safely: {error}")
        print(f"Diagnosis stopped safely: {error}")
        raise SystemExit(1) from error
    finally:
        store.close()


def execute(tools: InstrumentedTools, tool: str, arguments: dict[str, object]) -> ReadOnlyResult:
    if tool == "repo_map":
        return tools.repo_map()
    if tool == "search_code":
        query = arguments.get("query")
        return tools.search_code(query) if isinstance(query, str) and 2 <= len(query) <= 200 else ReadOnlyResult.failure("INVALID_PLAN", "invalid search query")
    path = arguments.get("path")
    return tools.read_file(path) if isinstance(path, str) else ReadOnlyResult.failure("INVALID_PLAN", "invalid read path")


def summarize(result: ReadOnlyResult) -> str:
    if not result.ok:
        return result.error.code if result.error else "tool failed"
    if isinstance(result.data, FileSlice):
        return f"read {result.data.path} lines {result.data.start_line}-{result.data.end_line}: {result.data.content[:1200]}"
    items = result.data or []
    return "items: " + (", ".join(str(item)[:180] for item in items[:8]) if items else "none")


def _next_allowed_tools(tool: str, result: ReadOnlyResult) -> set[str]:
    """Advance to reading only when a map/search produced a real path."""
    if tool in {"repo_map", "search_code"}:
        if not result.ok or not result.data:
            return {"repo_map", "search_code"}
        return {"search_code", "read_file"} if tool == "search_code" else {"read_file"}
    return READ_ONLY


if __name__ == "__main__":
    main()
