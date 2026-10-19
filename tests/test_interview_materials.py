import re
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_agent_architecture_documents_current_boundaries() -> None:
    content = (ROOT / "docs" / "agent-architecture.md").read_text(encoding="utf-8")

    assert "```mermaid" in content
    assert "Deterministic controller" in content
    assert "Qwen planner" in content
    assert "Disposable workspace" in content
    assert "SQLite" in content
    assert "awaiting_review" in content
    assert "needs_human" in content
    assert "13/13" in content
    assert "5/5" in content
    assert "1/1" in content


def test_interview_pitch_matches_frozen_metrics_and_demo_commands() -> None:
    content = (ROOT / "docs" / "interview-pitch.md").read_text(encoding="utf-8")

    for evidence in ("13/13", "5/5", "1/1", "179.6", "234"):
        assert evidence in content
    assert "PATCH_CONTEXT_MISMATCH" in content
    assert "python scripts\\showcase.py" in content
    assert "任意仓库 100% 修复" in content
    assert "qwen3.8-flash" in content

    timed_script = content.split("## 演示时的操作顺序", 1)[0]
    spoken = "".join(
        line[2:] for line in timed_script.splitlines() if line.startswith("> ")
    )
    chinese_characters = len(re.findall(r"[\u4e00-\u9fff]", spoken))
    assert 750 <= chinese_characters <= 1000
