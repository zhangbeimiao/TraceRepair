import json
import tomllib
from pathlib import Path

from tracerepair.version import (
    AGENT_VERSION,
    MAX_COMPLETION_TOKENS,
    MAX_MODEL_CALLS,
    MAX_TOTAL_COMPLETION_TOKENS,
    PROJECT_VERSION,
)


ROOT = Path(__file__).parents[1]


def test_project_version_matches_package_metadata() -> None:
    payload = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert payload["project"]["version"] == PROJECT_VERSION


def test_development_agent_does_not_relabel_frozen_historical_evidence() -> None:
    assert AGENT_VERSION == "0.8.0-dev2.1"
    assert MAX_COMPLETION_TOKENS == 800
    frozen = json.loads(
        (ROOT / "evaluation/frozen/historical-python-v1.0.0.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads(
        (ROOT / "evaluation/benchmarks/historical-python-v1.0.0.json").read_text(
            encoding="utf-8"
        )
    )
    development_v1 = json.loads(
        (ROOT / "evaluation/configs/agent-v0.6.0-dev1.json").read_text(
            encoding="utf-8"
        )
    )
    development_v2 = json.loads(
        (ROOT / "evaluation/configs/agent-v0.6.0-dev2.json").read_text(
            encoding="utf-8"
        )
    )
    development_v3 = json.loads(
        (ROOT / "evaluation/configs/agent-v0.6.0-dev3.json").read_text(
            encoding="utf-8"
        )
    )
    development_v4 = json.loads(
        (ROOT / "evaluation/configs/agent-v0.6.0-dev4.json").read_text(
            encoding="utf-8"
        )
    )
    langgraph_dev1 = json.loads(
        (ROOT / "evaluation/configs/agent-v0.7.0-dev1.json").read_text(
            encoding="utf-8"
        )
    )
    langgraph_dev2 = json.loads(
        (ROOT / "evaluation/configs/agent-v0.7.0-dev2.json").read_text(
            encoding="utf-8"
        )
    )
    initial_native = json.loads(
        (ROOT / "evaluation/configs/agent-v0.8.0-dev1.json").read_text(
            encoding="utf-8"
        )
    )
    native_development = json.loads(
        (ROOT / "evaluation/configs/agent-v0.8.0-dev1.1.json").read_text(
            encoding="utf-8"
        )
    )
    development = json.loads(
        (ROOT / "evaluation/configs/agent-v0.8.0-dev2.1.json").read_text(
            encoding="utf-8"
        )
    )

    assert development["agent_version"] == AGENT_VERSION
    assert native_development["status"] == "development_only_protocol_compatibility_revision"
    assert initial_native["agent_version"] == "0.8.0-dev1"
    assert native_development["parent_agent_version"] == "0.8.0-dev1"
    assert native_development["preserved_negative_evidence"]["result"].startswith("0/5 pass@1")
    assert development["parent_agent_version"] == "0.8.0-dev1.1"
    assert development["activation_gate"]["passed"] is True
    assert development_v1["agent_version"] == "0.6.0-dev1"
    assert development_v2["agent_version"] == "0.6.0-dev2"
    assert development_v3["agent_version"] == "0.6.0-dev3"
    assert development_v4["agent_version"] == "0.6.0-dev4"
    assert langgraph_dev1["agent_version"] == "0.7.0-dev1"
    assert langgraph_dev1["planner"]["max_calls_per_task"] == 4
    assert langgraph_dev1["planner"]["max_total_completion_tokens"] == 2048
    assert native_development["planner"]["max_completion_tokens"] == MAX_COMPLETION_TOKENS
    assert native_development["planner"]["max_calls_per_task"] == MAX_MODEL_CALLS == 5
    assert (
        native_development["planner"]["max_total_completion_tokens"]
        == MAX_TOTAL_COMPLETION_TOKENS
        == 3072
    )
    assert langgraph_dev2["agent_version"] == "0.7.0-dev2"
    assert native_development["architecture"] == "langgraph_end_to_end"
    assert native_development["planner_protocol"] == "native_function_calling"
    assert native_development["durable_state"] == "sqlite_only"
    assert native_development["langgraph_checkpointer"] is False
    assert native_development["semantic_review"]["execution_authority"] is False
    frozen_v06 = json.loads(
        (ROOT / "evaluation/frozen/agent-v0.6.0.json").read_text(encoding="utf-8")
    )
    assert frozen_v06["evaluated_runtime_agent_version"] == "0.6.0-dev4"
    assert frozen["agent_version"] == "0.5.0"
    assert frozen["summary"]["successes"] == 2
    assert frozen["summary"]["attempted_tasks"] == 3
    assert manifest["agent_version"] == "0.5.0"
