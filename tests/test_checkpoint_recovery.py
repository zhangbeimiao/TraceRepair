import json
from pathlib import Path

import pytest

from evaluation.materialize import materialize_case
from tracerepair.end_to_end_workflow import EndToEndRepairWorkflow
from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.model_planner import ModelPlanner, PlannerConfig
from tracerepair.models import Task, TaskStatus
from tracerepair.patch_apply import PatchApplier
from tracerepair.read_tools import ReadOnlyRepository
from tracerepair.recovery import InjectedCrash, PATCH_APPLIED, SOURCE_READ
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


SEARCH = (
    '{"kind":"tool","tool":"search_code",'
    '"arguments":{"query":"read_bool"},"reason":"locate parser"}'
)
READ = (
    '{"kind":"tool","tool":"read_file",'
    '"arguments":{"path":"src/eventrelay/config.py"},"reason":"inspect parser"}'
)
PATCH = json.dumps(
    {"kind": "patch", "unified_diff": FIX_CASE_05, "reason": "remove truthiness shortcut"}
)


class SequenceTransport:
    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)
        self.calls = 0

    def complete(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls += 1
        return {
            "choices": [{"message": {"content": next(self._responses)}}],
            "usage": {"completion_tokens": 30},
        }


class DeniedTransport:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls += 1
        raise AssertionError("verification recovery must not call the model")


def _create_task(tmp_path: Path) -> tuple[Path, Path]:
    workspace = materialize_case("05", tmp_path / "workspaces" / "model-agent" / "case-05")
    database = tmp_path / "trace.sqlite3"
    store = TraceStore(database)
    store.create_task(Task("agent-05", "05", "false parsed as true", str(workspace)))
    store.transition("agent-05", TaskStatus.READY, "ready")
    store.transition("agent-05", TaskStatus.RUNNING, "started")
    store.close()
    return database, workspace


def _workflow(
    database: Path,
    workspace: Path,
    transport: object,
    *,
    crash_after: str | None = None,
) -> tuple[TraceStore, EndToEndRepairWorkflow]:
    store = TraceStore(database)
    tools = InstrumentedTools(
        "agent-05",
        store,
        ReadOnlyRepository(workspace),
        RestrictedTestRunner(workspace),
        PatchApplier(workspace),
    )
    planner = ModelPlanner(
        transport,  # type: ignore[arg-type]
        PlannerConfig(
            max_completion_tokens=512,
            max_calls_per_task=4,
            max_total_completion_tokens=2_048,
        ),
    )
    return store, EndToEndRepairWorkflow(
        "agent-05", store, planner, tools, crash_after=crash_after
    )


def _resume_task(store: TraceStore) -> None:
    assert store.get_task("agent-05").status is TaskStatus.INTERRUPTED
    store.transition("agent-05", TaskStatus.READY, "operator requested checkpoint resume")
    store.transition("agent-05", TaskStatus.RUNNING, "checkpoint resume started")


def _started_tools(store: TraceStore) -> list[str]:
    return [
        str(event.payload["tool"])
        for event in store.list_events("agent-05")
        if event.event_type == "tool_started"
    ]


def test_resume_after_source_read_does_not_repeat_diagnosis_tools(tmp_path: Path) -> None:
    database, workspace = _create_task(tmp_path)
    first_transport = SequenceTransport([SEARCH, READ])
    store, workflow = _workflow(
        database, workspace, first_transport, crash_after=SOURCE_READ
    )

    with pytest.raises(InjectedCrash, match=SOURCE_READ):
        workflow.run("config value false must parse as False")

    checkpoint = store.load_checkpoint("agent-05")
    assert checkpoint["recovery"]["phase"] == SOURCE_READ
    assert "normalized = value" not in str(checkpoint)
    assert first_transport.calls == 2
    store.close()

    second_transport = SequenceTransport([PATCH])
    store = TraceStore(database)
    _resume_task(store)
    store.close()
    store, workflow = _workflow(database, workspace, second_transport)
    result = workflow.run("config value false must parse as False", resume=True)

    assert result.task_status is TaskStatus.AWAITING_REVIEW
    assert result.completion_tokens == 90
    assert second_transport.calls == 1
    assert _started_tools(store) == [
        "search_code",
        "read_file",
        "apply_patch",
        "run_tests",
        "run_regression",
    ]
    assert store.load_checkpoint("agent-05")["model_budget"]["calls"] == 3
    assert any(
        event.event_type == "workflow_resumed"
        for event in store.list_events("agent-05")
    )
    store.close()


def test_resume_after_patch_skips_model_and_patch_application(tmp_path: Path) -> None:
    database, workspace = _create_task(tmp_path)
    first_transport = SequenceTransport([SEARCH, READ, PATCH])
    store, workflow = _workflow(
        database, workspace, first_transport, crash_after=PATCH_APPLIED
    )

    with pytest.raises(InjectedCrash, match=PATCH_APPLIED):
        workflow.run("config value false must parse as False")

    assert store.load_checkpoint("agent-05")["recovery"]["phase"] == PATCH_APPLIED
    assert first_transport.calls == 3
    store.close()

    denied = DeniedTransport()
    store = TraceStore(database)
    _resume_task(store)
    store.close()
    store, workflow = _workflow(database, workspace, denied)
    result = workflow.run("config value false must parse as False", resume=True)

    assert result.task_status is TaskStatus.AWAITING_REVIEW
    assert denied.calls == 0
    assert _started_tools(store) == [
        "search_code",
        "read_file",
        "apply_patch",
        "run_tests",
        "run_regression",
    ]
    skipped = [
        event.payload
        for event in store.list_events("agent-05")
        if event.event_type == "recovery_step_skipped"
    ]
    assert any(item.get("tool") == "apply_patch" for item in skipped)
    store.close()


def test_resume_rejects_tampered_patched_workspace_before_tests(tmp_path: Path) -> None:
    database, workspace = _create_task(tmp_path)
    store, workflow = _workflow(
        database,
        workspace,
        SequenceTransport([SEARCH, READ, PATCH]),
        crash_after=PATCH_APPLIED,
    )
    with pytest.raises(InjectedCrash):
        workflow.run("config value false must parse as False")
    store.close()

    target = workspace / "src" / "eventrelay" / "config.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    store = TraceStore(database)
    _resume_task(store)
    store.close()
    denied = DeniedTransport()
    store, workflow = _workflow(database, workspace, denied)
    result = workflow.run("config value false must parse as False", resume=True)

    assert result.task_status is TaskStatus.NEEDS_HUMAN
    assert result.action == "resume"
    assert "integrity" in result.detail
    assert denied.calls == 0
    assert "run_tests" not in _started_tools(store)
    store.close()


def test_resume_rejects_tampered_source_artifact_before_model_call(tmp_path: Path) -> None:
    database, workspace = _create_task(tmp_path)
    store, workflow = _workflow(
        database,
        workspace,
        SequenceTransport([SEARCH, READ]),
        crash_after=SOURCE_READ,
    )
    with pytest.raises(InjectedCrash):
        workflow.run("config value false must parse as False")
    artifact = workspace / ".tracerepair" / "checkpoints" / "diagnosed-source.json"
    artifact.write_text(artifact.read_text(encoding="utf-8") + "tampered", encoding="utf-8")
    store.close()

    store = TraceStore(database)
    _resume_task(store)
    store.close()
    denied = DeniedTransport()
    store, workflow = _workflow(database, workspace, denied)
    result = workflow.run("config value false must parse as False", resume=True)

    assert result.task_status is TaskStatus.NEEDS_HUMAN
    assert "integrity" in result.detail
    assert denied.calls == 0
    assert "apply_patch" not in _started_tools(store)
    store.close()


def test_resume_reconciles_patch_result_committed_before_phase_marker(tmp_path: Path) -> None:
    database, workspace = _create_task(tmp_path)
    store, workflow = _workflow(
        database,
        workspace,
        SequenceTransport([SEARCH, READ, PATCH]),
        crash_after=PATCH_APPLIED,
    )
    with pytest.raises(InjectedCrash):
        workflow.run("config value false must parse as False")
    checkpoint = store.load_checkpoint("agent-05")
    checkpoint["recovery"]["phase"] = SOURCE_READ
    store.save_checkpoint("agent-05", checkpoint)
    store.close()

    store = TraceStore(database)
    _resume_task(store)
    store.close()
    denied = DeniedTransport()
    store, workflow = _workflow(database, workspace, denied)
    result = workflow.run("config value false must parse as False", resume=True)

    assert result.task_status is TaskStatus.AWAITING_REVIEW
    assert denied.calls == 0
    assert _started_tools(store).count("apply_patch") == 1
    assert any(
        event.event_type == "recovery_checkpoint_reconciled"
        for event in store.list_events("agent-05")
    )
    store.close()
