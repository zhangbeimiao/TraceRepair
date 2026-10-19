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
        "evaluation/frozen/repository-mini-repo-discount-v0.6.1.json",
        "evaluation/frozen/locked-repository-v0.6.1.json",
        "examples/tasks/mini-repo.json",
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
