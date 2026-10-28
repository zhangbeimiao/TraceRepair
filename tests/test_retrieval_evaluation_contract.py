import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_retrieval_ground_truth_is_development_only_and_has_distinct_repositories() -> None:
    path = ROOT / "evaluation" / "retrieval-ground-truth-v0.8.0-dev2.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["split"] == "development"
    assert len(payload["tasks"]) == 5
    configs = {task["task_config"] for task in payload["tasks"]}
    assert len(configs) == 5
    assert all(task["expected_paths"] for task in payload["tasks"])
    assert "diagnostic_queries are excluded" in payload["query_contract"]
    assert "do not support a generalisation claim" in payload["claim_boundary"]


def test_rag_benchmark_freezes_retrieval_settings_on_development_tasks() -> None:
    benchmark = json.loads(
        (ROOT / "evaluation" / "benchmarks" / "code-rag-v0.8.0-dev2.json").read_text(
            encoding="utf-8"
        )
    )
    config = json.loads(
        (ROOT / "evaluation" / "configs" / "agent-v0.8.0-dev2.json").read_text(
            encoding="utf-8"
        )
    )

    assert benchmark["agent_version"] == "0.8.0-dev2"
    assert {task["split"] for task in benchmark["tasks"]} == {"development"}
    assert benchmark["retrieval"] == {
        "mode": "hybrid",
        "chunker_version": "ast-symbol-v1",
        "embedding_model": "qwen3.7-text-embedding-flash",
        "embedding_dimensions": 256,
        "top_k": 5,
        "rrf_k": 60,
    }
    assert config["status"] == "planned_pending_semantic_retrieval_gate"


def test_file_level_rag_revision_is_versioned_and_does_not_authorize_execution() -> None:
    benchmark = json.loads(
        (ROOT / "evaluation/benchmarks/code-rag-v0.8.0-dev2.1.json").read_text(
            encoding="utf-8"
        )
    )
    config = json.loads(
        (ROOT / "evaluation/configs/agent-v0.8.0-dev2.1.json").read_text(
            encoding="utf-8"
        )
    )

    assert benchmark["protocol"] == "retrieval_gate_only"
    assert {task["split"] for task in benchmark["tasks"]} == {"development"}
    assert benchmark["retrieval"]["fusion"] == "file_level_reciprocal_rank_fusion"
    assert config["parent_agent_version"] == "0.8.0-dev1.1"
    assert config["retrieval"]["execution_authority"] is False
    assert config["evaluation_rule"].startswith("do not run repair or locked tasks")
