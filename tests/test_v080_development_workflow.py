from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "v080-development.yml"


def test_v080_online_workflow_is_manual_and_development_only() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in text
    assert "pull_request:" not in text
    assert "push:" not in text
    assert "--split development" in text
    assert "--split locked" not in text
    assert "--split all" not in text
    assert "function-calling-v0.8.0-dev1.1.json" in text
    assert "langgraph-blind" not in text


def test_v080_online_workflow_uses_secrets_without_echoing_values() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "secrets.DASHSCOPE_API_KEY" in text
    assert "secrets.TRACEREPAIR_BAILIAN_BASE_URL" in text
    assert 'echo "$DASHSCOPE_API_KEY"' not in text
    assert 'echo "$TRACEREPAIR_BAILIAN_BASE_URL"' not in text
    assert "actions/upload-artifact@v6" in text
