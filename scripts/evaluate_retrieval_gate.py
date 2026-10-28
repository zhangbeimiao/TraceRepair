"""Verify semantic retrieval evidence and decide the frozen dev2 activation gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation" / "results" / "code-retrieval-v0.8.0-dev2.1"
LEXICAL = RESULTS / "none.json"
SEMANTIC = RESULTS / "bailian.json"
OUTPUT = RESULTS / "activation-gate.json"


def _load_verified(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise SystemExit(f"retrieval report is missing: {path.relative_to(ROOT)}")
    checksum = path.with_suffix(path.suffix + ".sha256")
    if not checksum.is_file():
        raise SystemExit(f"retrieval checksum is missing: {checksum.relative_to(ROOT)}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if checksum.read_text(encoding="ascii").split()[0] != digest:
        raise SystemExit(f"retrieval checksum mismatch: {path.relative_to(ROOT)}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("summary"), dict):
        raise SystemExit(f"retrieval report has an invalid structure: {path.relative_to(ROOT)}")
    return payload


def build_gate() -> dict[str, object]:
    lexical = _load_verified(LEXICAL)
    semantic = _load_verified(SEMANTIC)
    if semantic.get("embedding_mode") != "bailian":
        raise SystemExit("semantic report must use the Bailian embedding provider")
    if semantic.get("embedding_model") != "qwen3.7-text-embedding-flash":
        raise SystemExit("semantic report used an unexpected embedding model")
    if semantic.get("embedding_dimensions") != 256:
        raise SystemExit("semantic report used unexpected embedding dimensions")
    lexical_tasks = [row.get("task") for row in lexical.get("tasks", [])]
    semantic_tasks = [row.get("task") for row in semantic.get("tasks", [])]
    if lexical_tasks != semantic_tasks or len(semantic_tasks) != 5:
        raise SystemExit("retrieval reports must contain the same five ordered development tasks")
    lexical_summary = lexical["summary"]
    semantic_summary = semantic["summary"]
    assert isinstance(lexical_summary, dict) and isinstance(semantic_summary, dict)
    baseline = {
        "file_recall_at_1": float(lexical_summary["lexical_file_recall_at_1"]),
        "file_recall_at_3": float(lexical_summary["lexical_file_recall_at_3"]),
        "file_recall_at_5": float(lexical_summary["lexical_file_recall_at_5"]),
        "mrr": float(lexical_summary["lexical_mrr"]),
    }
    candidate = {
        "file_recall_at_1": float(semantic_summary["hybrid_file_recall_at_1"]),
        "file_recall_at_3": float(semantic_summary["hybrid_file_recall_at_3"]),
        "file_recall_at_5": float(semantic_summary["hybrid_file_recall_at_5"]),
        "mrr": float(semantic_summary["hybrid_mrr"]),
    }
    recall5_preserved = candidate["file_recall_at_5"] >= baseline["file_recall_at_5"]
    ranking_improved = (
        candidate["file_recall_at_1"] > baseline["file_recall_at_1"]
        or candidate["mrr"] > baseline["mrr"]
    )
    passed = recall5_preserved and ranking_improved
    return {
        "schema_version": 1,
        "gate_id": "semantic-retrieval-activation-v0.8.0-dev2.1",
        "split": "known_development_tasks_only",
        "baseline": baseline,
        "candidate": candidate,
        "checks": {
            "recall_at_5_not_reduced": recall5_preserved,
            "recall_at_1_or_mrr_improved": ranking_improved,
        },
        "passed": passed,
        "decision": "activate_dev2" if passed else "keep_rag_disabled",
        "lexical_report_sha256": hashlib.sha256(LEXICAL.read_bytes()).hexdigest(),
        "semantic_report_sha256": hashlib.sha256(SEMANTIC.read_bytes()).hexdigest(),
        "rule": (
            "semantic hybrid must not reduce Recall@5 and must improve at least one of "
            "Recall@1 or MRR over FTS5"
        ),
        "claim_boundary": "Development retrieval gate only; it is not locked repair evidence.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-failed-gate", action="store_true")
    arguments = parser.parse_args()
    gate = build_gate()
    encoded = (json.dumps(gate, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    digest = hashlib.sha256(encoded).hexdigest()
    OUTPUT.write_bytes(encoded)
    OUTPUT.with_suffix(OUTPUT.suffix + ".sha256").write_text(
        f"{digest}  {OUTPUT.name}\n", encoding="ascii", newline="\n"
    )
    print(json.dumps(gate, ensure_ascii=False, indent=2))
    print(f"SHA-256: {digest}")
    if not gate["passed"] and not arguments.allow_failed_gate:
        raise SystemExit("semantic retrieval activation gate did not pass; RAG remains disabled")


if __name__ == "__main__":
    main()
