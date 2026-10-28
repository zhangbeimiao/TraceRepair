import json
from pathlib import Path

import pytest

from tracerepair.function_calling import NativeFunctionPlanner
from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.langgraph_end_to_end import LangGraphEndToEndRepairWorkflow
from tracerepair.model_planner import PlannerConfig
from tracerepair.models import Task, TaskStatus
from tracerepair.patch_apply import PatchApplier
from tracerepair.patch_policy import PatchPolicy
from tracerepair.read_tools import ReadOnlyRepository
from tracerepair.store import TraceStore
from tracerepair.test_runner import RestrictedTestRunner


class Sequence:
    def __init__(self):
        self.payloads = []
        self.calls = iter([
            ("search_code", {"query": "def __bool__", "max_hits": 10}),
            ("search_code", {"query": "def __len__", "max_hits": 10}),
            ("read_file", {"path": "pkg/core.py", "start_line": 1, "end_line": 20}),
            ("handoff", {"reason": "offline test"}),
        ])

    def complete(self, payload):
        self.payloads.append(payload)
        name, args = next(self.calls)
        return {"choices": [{"message": {"tool_calls": [{"id": "test", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}}], "usage": {"completion_tokens": 10}}


def test_missing_symbol_observes_registered_test_and_related_source(tmp_path):
    workspace = tmp_path / "repo"
    (workspace / "pkg/tests").mkdir(parents=True)
    (workspace / "pkg/core.py").write_text("class Widget:\n    def __len__(self):\n        return 1\n", encoding="utf-8")
    (workspace / "pkg/tests/test_widget.py").write_text("def test_bool():\n    assert bool(Widget())\n", encoding="utf-8")
    store = TraceStore(tmp_path / "trace.sqlite3")
    store.create_task(Task("missing", "case", "Widget bool behavior", str(workspace)))
    store.transition("missing", TaskStatus.READY, "ready")
    store.transition("missing", TaskStatus.RUNNING, "started")
    transport = Sequence()
    planner = NativeFunctionPlanner(transport, PlannerConfig(max_completion_tokens=100, max_calls_per_task=5, max_total_completion_tokens=500))
    tools = InstrumentedTools("missing", store, ReadOnlyRepository(workspace, allowed_roots=("pkg",)), RestrictedTestRunner(workspace), PatchApplier(workspace, PatchPolicy(allowed_roots=("pkg",))))
    graph = LangGraphEndToEndRepairWorkflow("missing", store, planner, tools, target_selector="pkg/tests/test_widget.py::test_bool", allowed_source_roots=("pkg",))
    result = graph.run("Widget bool behavior", diagnostic_queries=("class Widget", "def __len__"))
    assert result.task_status is TaskStatus.NEEDS_HUMAN
    next_evidence = transport.payloads[1]["messages"][1]["content"]
    assert "def __bool__" in next_evidence
    assert "def __len__" in next_evidence
    assert "assert bool(Widget())" in next_evidence
    assert "do not prove absence" in next_evidence
    patch_evidence = transport.payloads[-1]["messages"][1]["content"]
    assert "assert bool(Widget())" in patch_evidence
    assert "def __len__" in patch_evidence
    events = store.list_events("missing")
    assert sum(e.event_type == "registered_test_observed" for e in events) == 1
    assert not any(e.event_type == "tool_started" and e.payload["tool"] in {"apply_patch", "run_tests"} for e in events)
    store.close()


def test_known_tqdm_missing_symbol_exposes_real_test_and_len(tmp_path):
    original = Path(__file__).resolve().parents[1] / "evaluation/repositories/tqdm-sizeless-bool/tqdm"
    if not original.exists():
        pytest.skip("optional historical tqdm repository is not materialized")
    workspace = tmp_path / "tqdm-repo"
    (workspace / "tqdm/tests").mkdir(parents=True)
    for relative in ("_tqdm.py", "tests/tests_tqdm.py"):
        (workspace / "tqdm" / relative).write_bytes((original / relative).read_bytes())
    store = TraceStore(tmp_path / "tqdm.sqlite3")
    store.create_task(Task("tqdm-dev", "case", "tqdm bool behavior", str(workspace)))
    store.transition("tqdm-dev", TaskStatus.READY, "ready")
    store.transition("tqdm-dev", TaskStatus.RUNNING, "start")
    transport = Sequence()
    transport.calls = iter([
        ("search_code", {"query": "def __bool__", "max_hits": 10}),
        ("search_code", {"query": "def __len__", "max_hits": 10}),
        ("read_file", {"path": "tqdm/_tqdm.py", "start_line": 870, "end_line": 1069}),
        ("handoff", {"reason": "offline test stops before proposing a patch"}),
    ])
    planner = NativeFunctionPlanner(transport, PlannerConfig(max_completion_tokens=100, max_calls_per_task=5, max_total_completion_tokens=500, max_context_chars=12000))
    tools = InstrumentedTools("tqdm-dev", store, ReadOnlyRepository(workspace, allowed_roots=("tqdm",)), RestrictedTestRunner(workspace), PatchApplier(workspace, PatchPolicy(allowed_roots=("tqdm",))))
    graph = LangGraphEndToEndRepairWorkflow("tqdm-dev", store, planner, tools, target_selector="tqdm/tests/tests_tqdm.py::test_bool", allowed_source_roots=("tqdm",))
    result = graph.run("tqdm bool behavior", diagnostic_queries=("class tqdm", "def __len__", "def __bool__"))
    assert result.task_status is TaskStatus.NEEDS_HUMAN
    evidence = transport.payloads[-1]["messages"][1]["content"]
    assert "def __len__(self)" in evidence
    assert "get_bool_for_tqdm(total=10)" in evidence
    assert "get_bool_for_tqdm((x for x in []))" in evidence
    assert any(event.event_type == "registered_test_observed" for event in store.list_events("tqdm-dev"))
    store.close()
