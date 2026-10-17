import json
from pathlib import Path

from evaluation.materialize import materialize_case
from tracerepair.end_to_end_workflow import EndToEndRepairWorkflow
from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.model_planner import ModelPlanner, PlannerConfig
from tracerepair.models import Task, TaskStatus
from tracerepair.patch_apply import PatchApplier
from tracerepair.read_tools import ReadOnlyRepository
from tracerepair.store import TraceStore
from tracerepair.test_runner import RestrictedTestRunner


FIX_CASE_05 = """--- a/src/eventrelay/config.py
+++ b/src/eventrelay/config.py
@@ -6,6 +6,4 @@
     if value is None:
         return default
     normalized = value.strip().lower()
-    if value:
-        return True
     if normalized in {"1", "true", "yes", "on"}:
         return True
"""


class SequenceTransport:
    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)
        self.payloads: list[dict[str, object]] = []

    def complete(self, payload: dict[str, object]) -> dict[str, object]:
        self.payloads.append(dict(payload))
        return {
            "choices": [{"message": {"content": next(self._responses)}}],
            "usage": {"completion_tokens": 30},
        }


def make_workflow(
    tmp_path: Path, responses: list[str]
) -> tuple[TraceStore, SequenceTransport, EndToEndRepairWorkflow]:
    workspace = materialize_case("05", tmp_path / "case-05")
    store = TraceStore(tmp_path / "trace.sqlite3")
    task_id = "agent-05"
    store.create_task(Task(task_id, "05", "false parsed as true", str(workspace)))
    store.transition(task_id, TaskStatus.READY, "ready")
    store.transition(task_id, TaskStatus.RUNNING, "started")
    tools = InstrumentedTools(
        task_id,
        store,
        ReadOnlyRepository(workspace),
        RestrictedTestRunner(workspace),
        PatchApplier(workspace),
    )
    transport = SequenceTransport(responses)
    planner = ModelPlanner(
        transport,
        PlannerConfig(
            max_completion_tokens=512,
            max_calls_per_task=4,
            max_total_completion_tokens=2_048,
        ),
    )
    return store, transport, EndToEndRepairWorkflow(task_id, store, planner, tools)


def test_search_read_patch_runs_complete_verification_gate(tmp_path: Path) -> None:
    responses = [
        '{"kind":"tool","tool":"search_code","arguments":{"query":"read_bool"},"reason":"locate parser"}',
        '{"kind":"tool","tool":"read_file","arguments":{"path":"src/eventrelay/config.py"},"reason":"inspect parser"}',
        json.dumps({"kind": "patch", "unified_diff": FIX_CASE_05, "reason": "remove truthiness shortcut"}),
    ]
    store, transport, workflow = make_workflow(tmp_path, responses)

    result = workflow.run("config value false must parse as False")

    assert result.task_status is TaskStatus.AWAITING_REVIEW
    assert result.action == "run_regression"
    assert result.diagnosis_turns == 2
    assert result.completion_tokens == 90
    assert store.load_checkpoint("agent-05")["model_budget"]["calls"] == 3
    tools = [item["tool"] for item in store.load_checkpoint("agent-05")["completed_tools"]]
    assert tools == ["search_code", "read_file", "apply_patch", "run_tests", "run_regression"]
    assert "unified_diff" not in transport.payloads[0]["messages"][0]["content"]
    assert '"kind":"tool"' not in transport.payloads[2]["messages"][0]["content"]
    store.close()


def test_early_handoff_stops_without_tools_or_patch(tmp_path: Path) -> None:
    store, _, workflow = make_workflow(
        tmp_path, ['{"kind":"handoff","reason":"insufficient evidence"}']
    )

    result = workflow.run("ambiguous issue")

    assert result.task_status is TaskStatus.NEEDS_HUMAN
    assert result.action == "handoff"
    assert store.load_checkpoint("agent-05").get("completed_tools", []) == []
    store.close()


def test_broad_search_must_be_refined_before_reading(tmp_path: Path) -> None:
    responses = [
        '{"kind":"tool","tool":"search_code","arguments":{"query":"EventRelay"},"reason":"broad search"}',
        '{"kind":"tool","tool":"search_code","arguments":{"query":"false"},"reason":"refine by literal"}',
        '{"kind":"tool","tool":"read_file","arguments":{"path":"src/eventrelay/config.py"},"reason":"inspect relevant parser"}',
        json.dumps({"kind": "patch", "unified_diff": FIX_CASE_05, "reason": "remove truthiness shortcut"}),
    ]
    store, transport, workflow = make_workflow(tmp_path, responses)

    result = workflow.run("config value 'false' must parse as False")

    assert result.task_status is TaskStatus.AWAITING_REVIEW
    assert result.diagnosis_turns == 3
    second_prompt = transport.payloads[1]["messages"][0]["content"]
    assert '"tool":"search_code"' in second_prompt
    assert "read_file" not in second_prompt
    store.close()


def test_irrelevant_read_uses_quoted_literal_fallback(tmp_path: Path) -> None:
    responses = [
        '{"kind":"tool","tool":"repo_map","arguments":{},"reason":"list files"}',
        '{"kind":"tool","tool":"read_file","arguments":{"path":"src/eventrelay/processor.py"},"reason":"inspect candidate"}',
        json.dumps({"kind": "patch", "unified_diff": FIX_CASE_05, "reason": "remove truthiness shortcut"}),
    ]
    store, _, workflow = make_workflow(tmp_path, responses)

    result = workflow.run("config value 'false' must parse as False")

    assert result.task_status is TaskStatus.AWAITING_REVIEW
    tools = [item["tool"] for item in store.load_checkpoint("agent-05")["completed_tools"]]
    assert tools[:4] == ["repo_map", "read_file", "search_code", "read_file"]
    recovery = [event for event in store.list_events("agent-05") if event.event_type == "deterministic_recovery"]
    assert recovery[0].payload["path"] == "src/eventrelay/config.py"
    store.close()


def test_last_search_turn_reads_a_unique_relevant_path_without_another_model_call(
    tmp_path: Path,
) -> None:
    responses = [
        '{"kind":"tool","tool":"search_code","arguments":{"query":"EventRelay"},"reason":"broad"}',
        '{"kind":"tool","tool":"search_code","arguments":{"query":"parse_event"},"reason":"still broad"}',
        '{"kind":"tool","tool":"search_code","arguments":{"query":"false"},"reason":"task literal"}',
        json.dumps({"kind": "patch", "unified_diff": FIX_CASE_05, "reason": "remove truthiness shortcut"}),
    ]
    store, transport, workflow = make_workflow(tmp_path, responses)

    result = workflow.run("config value 'false' must parse as False")

    assert result.task_status is TaskStatus.AWAITING_REVIEW
    assert result.diagnosis_turns == 3
    assert len(transport.payloads) == 4
    tools = [item["tool"] for item in store.load_checkpoint("agent-05")["completed_tools"]]
    assert tools[:4] == ["search_code", "search_code", "search_code", "read_file"]
    store.close()


def test_exhausted_model_searches_recover_from_public_entrypoint_hint(tmp_path: Path) -> None:
    responses = [
        '{"kind":"tool","tool":"search_code","arguments":{"query":"EventRelay"},"reason":"broad"}',
        '{"kind":"tool","tool":"search_code","arguments":{"query":"parse_event"},"reason":"wrong area"}',
        '{"kind":"tool","tool":"search_code","arguments":{"query":"missing_symbol"},"reason":"no match"}',
        json.dumps({"kind": "patch", "unified_diff": FIX_CASE_05, "reason": "remove truthiness shortcut"}),
    ]
    store, _, workflow = make_workflow(tmp_path, responses)

    result = workflow.run(
        "config value false must parse as False",
        diagnostic_queries=("def read_bool",),
    )

    assert result.task_status is TaskStatus.AWAITING_REVIEW
    recoveries = [
        event.payload
        for event in store.list_events("agent-05")
        if event.event_type == "deterministic_recovery"
    ]
    assert recoveries[-1] == {
        "trigger": "diagnosis_exhausted",
        "action": "read_file",
        "path": "src/eventrelay/config.py",
    }
    store.close()
