"""Evaluate lexical and hybrid code retrieval on known development tasks."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tracerepair.code_retrieval import (
    BailianEmbeddingProvider,
    CodeIndex,
    HashEmbeddingProvider,
    retrieval_metrics,
)
from tracerepair.repository_task import RepositoryTaskSpec


GROUND_TRUTH = ROOT / "evaluation" / "retrieval-ground-truth-v0.8.0-dev2.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--embedding",
        choices=("none", "hash", "bailian"),
        default="hash",
        help="hash is an offline vector-path baseline, not a learned semantic model",
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if not 1 <= arguments.limit <= 30:
        parser.error("--limit must be between 1 and 30")
    provider = None
    if arguments.embedding == "hash":
        provider = HashEmbeddingProvider()
    elif arguments.embedding == "bailian":
        provider = BailianEmbeddingProvider()

    ground_truth = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    totals = {
        "lexical_file_recall_at_1": 0.0,
        "lexical_file_recall_at_3": 0.0,
        "lexical_file_recall_at_5": 0.0,
        "lexical_mrr": 0.0,
        "vector_file_recall_at_1": 0.0,
        "vector_file_recall_at_3": 0.0,
        "vector_file_recall_at_5": 0.0,
        "vector_mrr": 0.0,
        "hybrid_file_recall_at_1": 0.0,
        "hybrid_file_recall_at_3": 0.0,
        "hybrid_file_recall_at_5": 0.0,
        "hybrid_mrr": 0.0,
    }
    for entry in ground_truth["tasks"]:
        config = (ROOT / "evaluation" / entry["task_config"]).resolve()
        spec = RepositoryTaskSpec.load(config)
        model_name = provider.model_id if provider is not None else "lexical-only"
        safe_model = model_name.replace("/", "-").replace("\\", "-")
        database = ROOT / "data" / "retrieval" / f"{spec.name}-{safe_model}.sqlite3"
        with CodeIndex(database) as index:
            built = index.build(
                spec.repository_root,
                allowed_roots=spec.source_allowlist,
                embedding_provider=provider,
            )
            query = f"{spec.issue} Failing pytest selector: {spec.target_test}"
            lexical = index.lexical_search(query, limit=arguments.limit)
            vector = (
                index.vector_search(query, provider, limit=arguments.limit)
                if provider is not None
                else []
            )
            hybrid = index.hybrid_file_search(
                query, embedding_provider=provider, limit=arguments.limit
            )
            expected = set(entry["expected_paths"])
            lexical_metrics = retrieval_metrics(lexical, expected)
            vector_metrics = retrieval_metrics(vector, expected)
            hybrid_metrics = retrieval_metrics(hybrid, expected)
            row = {
                "task": spec.name,
                "expected_paths": sorted(expected),
                "repository_sha256": built.repository_sha256,
                "chunks": built.chunks,
                "files": built.files,
                "embedding_model": built.embedding_model,
                "embedding_dimensions": built.embedding_dimensions,
                "lexical": {
                    **lexical_metrics,
                    "top_paths": list(dict.fromkeys(hit.chunk.path for hit in lexical))[:5],
                },
                "vector": {
                    **vector_metrics,
                    "top_paths": list(dict.fromkeys(hit.chunk.path for hit in vector))[:5],
                },
                "hybrid": {
                    **hybrid_metrics,
                    "top_paths": list(dict.fromkeys(hit.chunk.path for hit in hybrid))[:5],
                },
            }
            rows.append(row)
            for metric, value in lexical_metrics.items():
                totals[f"lexical_{metric}"] += value
            for metric, value in vector_metrics.items():
                totals[f"vector_{metric}"] += value
            for metric, value in hybrid_metrics.items():
                totals[f"hybrid_{metric}"] += value
            print(
                f"{spec.name}: lexical R@5={lexical_metrics['file_recall_at_5']:.0f} "
                f"MRR={lexical_metrics['mrr']:.3f}; hybrid R@5="
                f"{hybrid_metrics['file_recall_at_5']:.0f} MRR={hybrid_metrics['mrr']:.3f}"
            )
    count = len(rows)
    summary = {key: round(value / count, 4) for key, value in totals.items()}
    result = {
        "schema_version": 1,
        "evaluation_id": "code-retrieval-v0.8.0-dev2.1",
        "split": "development",
        "embedding_mode": arguments.embedding,
        "embedding_model": provider.model_id if provider is not None else None,
        "embedding_dimensions": provider.dimensions if provider is not None else None,
        "fusion": "file-level reciprocal rank fusion",
        "index_cache": "reuse only when repository, chunker, roots, model, dimensions and counts match",
        "query_contract": ground_truth["query_contract"],
        "tasks": rows,
        "summary": summary,
        "claim_boundary": ground_truth["claim_boundary"],
    }
    encoded = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    output = arguments.output or (
        ROOT / "evaluation" / "results" / "code-retrieval-v0.8.0-dev2.1" / f"{arguments.embedding}.json"
    )
    output = output.resolve()
    if not output.is_relative_to(ROOT.resolve()) or output.drive.casefold() == "c:":
        parser.error("output must remain inside the D: project")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encoded)
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{digest}  {output.name}\n", encoding="ascii", newline="\n"
    )
    print("Retrieval development evaluation completed.")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Report: {output.relative_to(ROOT)}")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
