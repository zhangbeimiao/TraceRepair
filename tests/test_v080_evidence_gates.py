from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_report(path: Path, *, mode: str, summary: dict[str, float]) -> None:
    payload = {
        "embedding_mode": mode,
        "embedding_model": "qwen3.7-text-embedding-flash" if mode == "bailian" else None,
        "embedding_dimensions": 256 if mode == "bailian" else None,
        "tasks": [{"task": f"task-{index}"} for index in range(5)],
        "summary": summary,
    }
    encoded = (json.dumps(payload) + "\n").encode()
    path.write_bytes(encoded)
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{hashlib.sha256(encoded).hexdigest()}  {path.name}\n", encoding="ascii"
    )


def test_prompt_security_report_covers_host_containment_contract() -> None:
    module = _load_script("evaluate_prompt_security.py")
    report = module.build_report()

    assert report["summary"] == {
        "cases": 7,
        "passed": 7,
        "failed": 0,
        "containment_rate": 1.0,
    }
    assert {case["case_id"] for case in report["cases"]} == {
        "untrusted-delimiter-and-secret-request",
        "unknown-tool",
        "path-traversal",
        "stage-jump",
            "compatibility-alias-stage-jump",
        "regex-command-chain",
        "parallel-calls",
    }
    assert "do not measure an LLM" in report["claim_boundary"]


def test_semantic_retrieval_gate_passes_only_with_preserved_recall_and_better_ranking(
    tmp_path: Path,
) -> None:
    module = _load_script("evaluate_retrieval_gate.py")
    lexical = tmp_path / "none.json"
    semantic = tmp_path / "bailian.json"
    baseline = {
        "lexical_file_recall_at_1": 0.6,
        "lexical_file_recall_at_3": 0.8,
        "lexical_file_recall_at_5": 1.0,
        "lexical_mrr": 0.75,
    }
    _write_report(lexical, mode="none", summary=baseline)
    _write_report(
        semantic,
        mode="bailian",
        summary={
            "hybrid_file_recall_at_1": 0.8,
            "hybrid_file_recall_at_3": 1.0,
            "hybrid_file_recall_at_5": 1.0,
            "hybrid_mrr": 0.9,
        },
    )
    module.LEXICAL = lexical
    module.SEMANTIC = semantic

    gate = module.build_gate()

    assert gate["passed"] is True
    assert gate["decision"] == "activate_dev2"

    _write_report(
        semantic,
        mode="bailian",
        summary={
            "hybrid_file_recall_at_1": 0.8,
            "hybrid_file_recall_at_3": 0.8,
            "hybrid_file_recall_at_5": 0.8,
            "hybrid_mrr": 0.9,
        },
    )
    gate = module.build_gate()
    assert gate["passed"] is False
    assert gate["decision"] == "keep_rag_disabled"
