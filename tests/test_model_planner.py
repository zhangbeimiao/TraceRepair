import json
from pathlib import Path

import pytest

from tracerepair.model_planner import BudgetExceeded, ModelPlanner, PlannerConfig, PlannerError
from tracerepair.models import Task
from tracerepair.store import TraceStore


class FakeTransport:
    def __init__(self, content: str, completion_tokens: int = 42) -> None:
        self.content = content
        self.completion_tokens = completion_tokens
        self.payloads: list[dict[str, object]] = []

    def complete(self, payload: dict[str, object]) -> dict[str, object]:
        self.payloads.append(dict(payload))
        return {
            "choices": [{"message": {"content": self.content}}],
            "usage": {"completion_tokens": self.completion_tokens},
        }


def planner_store(tmp_path: Path) -> TraceStore:
    store = TraceStore(tmp_path / "trace.sqlite3")
    store.create_task(Task("planner-01", "01", "wrong idempotency key", "D:/case"))
    return store


def test_planner_uses_small_deterministic_request_and_records_metadata(tmp_path: Path) -> None:
    transport = FakeTransport(
        '{"kind":"tool","tool":"search_code","arguments":{"query":"idempotency"},"reason":"find implementation"}'
    )
    store = planner_store(tmp_path)
    planner = ModelPlanner(transport)

    plan = planner.suggest("planner-01", store, "x" * 12_000)

    assert plan.tool == "search_code"
    assert transport.payloads[0]["temperature"] == 0
    assert transport.payloads[0]["max_tokens"] == 700
    assert transport.payloads[0]["enable_thinking"] is False
    assert transport.payloads[0]["response_format"] == {"type": "json_object"}
    assert "plain literal substring" in transport.payloads[0]["messages"][0]["content"]
    assert len(transport.payloads[0]["messages"][1]["content"]) <= 9_010
    checkpoint = store.load_checkpoint("planner-01")
    assert checkpoint["model_budget"]["calls"] == 1
    event = store.list_events("planner-01")[-1]
    assert event.event_type == "model_plan_recorded"
    assert "idempotency" not in str(event.payload)
    store.close()


def test_denied_tool_is_not_recorded_or_executed(tmp_path: Path) -> None:
    transport = FakeTransport('{"kind":"tool","tool":"shell","arguments":{"command":"del"},"reason":"bad"}')
    store = planner_store(tmp_path)

    with pytest.raises(PlannerError, match="denied tool"):
        ModelPlanner(transport).suggest("planner-01", store, "evidence")

    assert store.load_checkpoint("planner-01")["model_budget"]["calls"] == 1
    assert store.list_events("planner-01")[-1].payload["policy_accepted"] is False
    store.close()


def test_call_budget_blocks_a_second_provider_request(tmp_path: Path) -> None:
    transport = FakeTransport('{"kind":"handoff","reason":"uncertain"}')
    store = planner_store(tmp_path)
    planner = ModelPlanner(transport, PlannerConfig(max_calls_per_task=1, max_total_completion_tokens=700))
    planner.suggest("planner-01", store, "evidence")

    with pytest.raises(BudgetExceeded):
        planner.suggest("planner-01", store, "evidence")

    assert len(transport.payloads) == 1
    store.close()


def test_harmless_stop_alias_becomes_handoff(tmp_path: Path) -> None:
    transport = FakeTransport('{"kind":"done","reason":"enough evidence"}')
    store = planner_store(tmp_path)

    plan = ModelPlanner(transport).suggest("planner-01", store, "evidence")

    assert plan.kind == "handoff"
    store.close()


def test_stage_allowlist_rejects_repeated_wrong_tool(tmp_path: Path) -> None:
    transport = FakeTransport(
        '{"kind":"tool","tool":"search_code","arguments":{"query":"config"},"reason":"repeat"}'
    )
    store = planner_store(tmp_path)

    with pytest.raises(PlannerError, match="current stage"):
        ModelPlanner(transport).suggest("planner-01", store, "evidence", allowed_tools={"read_file"})

    assert store.load_checkpoint("planner-01")["model_budget"]["calls"] == 1
    assert store.list_events("planner-01")[-1].payload["policy_accepted"] is False
    store.close()


def test_read_only_stage_does_not_advertise_patch_schema(tmp_path: Path) -> None:
    transport = FakeTransport('{"kind":"handoff","reason":"diagnosis complete"}')
    store = planner_store(tmp_path)

    plan = ModelPlanner(transport).suggest(
        "planner-01", store, "evidence", allowed_tools={"read_file"}, allow_patch=False
    )

    system_prompt = transport.payloads[0]["messages"][0]["content"]
    assert plan.kind == "handoff"
    assert "unified_diff" not in system_prompt
    store.close()


def test_json_inside_generic_markdown_fence_is_accepted(tmp_path: Path) -> None:
    transport = FakeTransport('```\n{"kind":"handoff","reason":"done"}\n```')
    store = planner_store(tmp_path)

    plan = ModelPlanner(transport).suggest("planner-01", store, "evidence")

    assert plan.kind == "handoff"
    store.close()


def test_patch_stage_does_not_advertise_tools(tmp_path: Path) -> None:
    transport = FakeTransport('{"kind":"handoff","reason":"need more evidence"}')
    store = planner_store(tmp_path)

    ModelPlanner(transport).suggest(
        "planner-01", store, "source evidence", allowed_tools=set(), allow_patch=True
    )

    system_prompt = transport.payloads[0]["messages"][0]["content"]
    assert '"kind":"tool"' not in system_prompt
    assert "unified_diff" in system_prompt
    store.close()


def test_standard_git_diff_header_is_accepted_in_patch_stage(tmp_path: Path) -> None:
    diff = (
        "diff --git a/src/eventrelay/config.py b/src/eventrelay/config.py\n"
        "--- a/src/eventrelay/config.py\n"
        "+++ b/src/eventrelay/config.py\n"
        "@@ -1,1 +1,1 @@\n-import os\n+import os\n"
    )
    transport = FakeTransport(
        json.dumps({"kind": "patch", "unified_diff": diff, "reason": "small fix"})
    )
    store = planner_store(tmp_path)

    plan = ModelPlanner(transport).suggest(
        "planner-01", store, "source evidence", allowed_tools=set(), allow_patch=True
    )

    assert plan.kind == "patch"
    assert plan.unified_diff is not None and plan.unified_diff.startswith("diff --git a/")
    store.close()


def test_fenced_diff_is_normalized_but_begin_patch_format_is_rejected(tmp_path: Path) -> None:
    diff = (
        "```diff\n--- a/src/eventrelay/config.py\n+++ b/src/eventrelay/config.py\n"
        "@@ -1,1 +1,1 @@\n-import os\n+import os\n```"
    )
    transport = FakeTransport(
        json.dumps({"kind": "patch", "unified_diff": diff, "reason": "small fix"})
    )
    store = planner_store(tmp_path)
    plan = ModelPlanner(transport).suggest(
        "planner-01", store, "source evidence", allowed_tools=set(), allow_patch=True
    )
    assert plan.unified_diff is not None and plan.unified_diff.startswith("--- a/")
    store.close()

    denied_transport = FakeTransport(
        '{"kind":"patch","unified_diff":"*** Begin Patch\\n*** End Patch","reason":"wrong format"}'
    )
    denied_dir = tmp_path / "denied"
    denied_dir.mkdir()
    denied_store = planner_store(denied_dir)
    with pytest.raises(PlannerError, match="headers"):
        ModelPlanner(denied_transport).suggest(
            "planner-01", denied_store, "source evidence", allowed_tools=set(), allow_patch=True
        )
    event = denied_store.list_events("planner-01")[-1]
    assert event.payload["parse_error"] == "model patch has invalid unified diff headers"
    assert len(event.payload["response_sha256"]) == 64
    denied_store.close()
