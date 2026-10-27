from pathlib import Path

from scripts.verify_release import verify


def make_release_tree(root: Path) -> None:
    for relative in (
        "evaluation/frozen/devset-v0.4.0-dev1.json",
        "evaluation/frozen/testset-v0.4.0-dev1.json",
        "evaluation/frozen/release-summary-v0.4.0-dev1.json",
        "evaluation/frozen/failure-showcase-v0.4.0.json",
        "evaluation/frozen/recovery-showcase-v0.4.1.json",
        "docs/releases/v0.6.0.md",
        "docs/releases/v0.6.1.md",
        "docs/releases/agent-v0.6.0.md",
        "docs/agent-architecture.md",
        "docs/interview-pitch.md",
        "docs/patch-location-v0.6.0-dev1.md",
        "docs/resume-material.md",
        "evaluation/configs/agent-v0.6.0-dev1.json",
        "evaluation/configs/agent-v0.6.0-dev4.json",
        "evaluation/benchmarks/historical-python-v1.0.0.json",
        "evaluation/benchmarks/historical-python-v1.1.3.json",
        "evaluation/benchmarks/langgraph-blind-v0.7.0-dev2.json",
        "evaluation/benchmarks/langgraph-blind-extension-v0.7.0-dev2.json",
        "evaluation/benchmarks/langgraph-review-offline-v0.7.0-dev2.json",
        "evaluation/frozen/agent-v0.5.0.json",
        "evaluation/frozen/agent-v0.6.0.json",
        "evaluation/frozen/agent-v0.7.0-dev2.json",
        "evaluation/frozen/historical-python-v1.0.0.json",
        "evaluation/frozen/historical-python-v1.0.0.json.sha256",
        "evaluation/frozen/release-summary-v0.5.0.json",
        "evaluation/frozen/historical-python-v1.1.3.json",
        "evaluation/frozen/historical-python-v1.1.3.json.sha256",
        "evaluation/frozen/langgraph-review-offline-v0.7.0-dev2.json",
        "evaluation/frozen/langgraph-review-offline-v0.7.0-dev2.json.sha256",
        "evaluation/frozen/langgraph-blind-v0.7.0-dev2-preflight.json",
        "evaluation/frozen/langgraph-blind-v0.7.0-dev2-preflight.json.sha256",
        "evaluation/frozen/langgraph-blind-extension-v0.7.0-dev2-preflight.json",
        "evaluation/frozen/langgraph-blind-extension-v0.7.0-dev2-preflight.json.sha256",
        "evaluation/frozen/langgraph-blind-extension-v0.7.0-dev2.json",
        "evaluation/frozen/langgraph-blind-extension-v0.7.0-dev2.json.sha256",
        "evaluation/frozen/langgraph-blind-six-repository-v0.7.0-dev2.json",
        "evaluation/frozen/langgraph-blind-six-repository-v0.7.0-dev2.json.sha256",
        "evaluation/frozen/langgraph-blind-v0.7.0-dev2.json",
        "evaluation/frozen/langgraph-blind-v0.7.0-dev2.json.sha256",
        "evaluation/frozen/release-summary-v0.6.0.json",
        "evaluation/results/historical-python-v1.0.0/attempts.jsonl",
        "evaluation/results/historical-python-v1.0.0/report.json",
        "evaluation/results/historical-python-v1.0.0/report.json.sha256",
        "evaluation/results/historical-python-v1.1.3/attempts.jsonl",
        "evaluation/results/historical-python-v1.1.3/report.json",
        "evaluation/results/historical-python-v1.1.3/report.json.sha256",
        "evaluation/results/langgraph-review-offline-v0.7.0-dev2/attempts.jsonl",
        "evaluation/results/langgraph-review-offline-v0.7.0-dev2/report.json",
        "evaluation/results/langgraph-review-offline-v0.7.0-dev2/report.json.sha256",
        "evaluation/results/langgraph-review-offline-v0.7.0-dev2/DEVELOPMENT_FINDINGS.md",
        "evaluation/results/langgraph-review-offline-v0.7.0-dev2/failures/tqdm-sizeless-bool.diff",
        "evaluation/results/langgraph-review-offline-v0.7.0-dev2/failures/tqdm-sizeless-bool.json",
        "evaluation/results/langgraph-blind-v0.7.0-dev2/attempts.jsonl",
        "evaluation/results/langgraph-blind-v0.7.0-dev2/manifest.lock.json",
        "evaluation/results/langgraph-blind-v0.7.0-dev2/report.json",
        "evaluation/results/langgraph-blind-v0.7.0-dev2/report.json.sha256",
        "evaluation/results/langgraph-blind-v0.7.0-dev2/logs/toolz-empty-interpose.log",
        "evaluation/results/langgraph-blind-v0.7.0-dev2/logs/prettytable-horizontal-align.log",
        "evaluation/results/langgraph-blind-v0.7.0-dev2/logs/glom-path-index-boundary.log",
        "evaluation/results/langgraph-blind-v0.7.0-dev2/LOCKED_FINDINGS.md",
        "evaluation/results/langgraph-blind-v0.7.0-dev2/failures/prettytable-horizontal-align.diff",
        "evaluation/results/langgraph-blind-v0.7.0-dev2/failures/prettytable-horizontal-align.json",
        "evaluation/results/langgraph-blind-v0.7.0-dev2/failures/glom-path-index-boundary.diff",
        "evaluation/results/langgraph-blind-v0.7.0-dev2/failures/glom-path-index-boundary.json",
        "evaluation/results/langgraph-blind-extension-v0.7.0-dev2/attempts.jsonl",
        "evaluation/results/langgraph-blind-extension-v0.7.0-dev2/manifest.lock.json",
        "evaluation/results/langgraph-blind-extension-v0.7.0-dev2/report.json",
        "evaluation/results/langgraph-blind-extension-v0.7.0-dev2/report.json.sha256",
        "evaluation/results/langgraph-blind-extension-v0.7.0-dev2/LOCKED_FINDINGS.md",
        "evaluation/results/langgraph-blind-extension-v0.7.0-dev2/logs/cachetools-falsey-getsizeof.log",
        "evaluation/results/langgraph-blind-extension-v0.7.0-dev2/logs/python-slugify-invalid-types.log",
        "evaluation/results/langgraph-blind-extension-v0.7.0-dev2/logs/click-sentinel-copy.log",
        "evaluation/results/langgraph-blind-extension-v0.7.0-dev2/failures/cachetools-falsey-getsizeof.json",
        "evaluation/results/langgraph-blind-extension-v0.7.0-dev2/failures/click-sentinel-copy.json",
        "evaluation/results/langgraph-blind-extension-v0.7.0-dev2/successes/python-slugify-invalid-types.diff",
        "evaluation/results/langgraph-blind-extension-v0.7.0-dev2/successes/python-slugify-invalid-types.json",
        "scripts/verify_blind_evidence.py",
        "evaluation/frozen/repository-mini-repo-discount-v0.6.1.json",
        "evaluation/frozen/locked-repository-v0.6.1.json",
        "examples/tasks/mini-repo.json",
        "scripts/showcase.py",
        "scripts/verify_benchmark_evidence.py",
        "demo/dist/index.html",
        "demo/dist/data.js",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")


def test_release_verifier_accepts_placeholder_configuration(tmp_path: Path) -> None:
    make_release_tree(tmp_path)
    (tmp_path / ".env.example").write_text(
        "DASHSCOPE_API_KEY=\n"
        "TRACEREPAIR_BAILIAN_BASE_URL=https://YOUR_WORKSPACE_ID.example.invalid/v1\n",
        encoding="utf-8",
    )
    assert verify(tmp_path) == []


def test_release_verifier_reports_secret_without_echoing_it(tmp_path: Path) -> None:
    make_release_tree(tmp_path)
    secret = "sk-" + "ws-" + "example-secret-value-that-must-not-be-printed"
    (tmp_path / "unsafe.txt").write_text(secret, encoding="utf-8")
    violations = verify(tmp_path)

    assert violations == ["API key literal: unsafe.txt"]
    assert secret not in "\n".join(violations)
