import hashlib
from pathlib import Path

import pytest

from tracerepair.demo_evidence import (
    DemoEvidenceError,
    build_failure_control_summary,
    build_patch_preview,
    build_verification_summary,
)
from tracerepair.showcase import ShowcaseTrace


def _successful_trace(workspace: Path, content: str) -> ShowcaseTrace:
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    events = (
        (
            "model_plan_recorded",
            {"kind": "patch", "policy_accepted": True, "completion_tokens": 40},
        ),
        (
            "tool_started",
            {"tool": "apply_patch", "arguments": {"diff_sha256": "a" * 64}},
        ),
        (
            "tool_finished",
            {
                "tool": "apply_patch",
                "ok": True,
                "error_code": None,
                "summary": {
                    "files": ["src/eventrelay/config.py"],
                    "file_sha256": {"src/eventrelay/config.py": content_hash},
                },
            },
        ),
        (
            "tool_finished",
            {
                "tool": "run_tests",
                "ok": True,
                "summary": {"duration_ms": 12, "exit_code": 0},
            },
        ),
        (
            "tool_finished",
            {
                "tool": "run_regression",
                "ok": True,
                "summary": {"duration_ms": 24, "exit_code": 0},
            },
        ),
        (
            "status_changed",
            {"from": "running", "to": "awaiting_review", "reason": "all tests passed"},
        ),
    )
    return ShowcaseTrace(
        task_id="model-agent-demo",
        case_id="05",
        issue="false enables retries",
        status="awaiting_review",
        agent_version="0.4.0-dev1",
        model="fake",
        events=events,
        workspace=str(workspace),
    )


def test_patch_preview_is_reconstructed_and_digest_verified(tmp_path: Path) -> None:
    baseline_root = tmp_path / "project"
    workspace = baseline_root / "workspaces" / "model-agent" / "case-demo"
    relative = Path("src/eventrelay/config.py")
    correct = "def enabled(value: str) -> bool:\n    return value == 'true'\n"
    for root in (baseline_root, workspace):
        (root / relative).parent.mkdir(parents=True)
        (root / relative).write_text(correct, encoding="utf-8")
    case = {
        "file": relative.as_posix(),
        "find": "    return value == 'true'",
        "replace": "    return bool(value)",
    }

    preview = build_patch_preview(_successful_trace(workspace, correct), case, baseline_root)

    assert preview["file"] == relative.as_posix()
    assert preview["diffSha256"] == "a" * 64
    assert preview["addedLines"] == 1
    assert preview["removedLines"] == 1
    rendered = "\n".join(line["text"] for line in preview["lines"])
    assert "+    return value == 'true'" in rendered
    assert "-    return bool(value)" in rendered
    assert str(workspace) not in rendered


def test_patch_preview_rejects_workspace_that_does_not_match_trace_hash(tmp_path: Path) -> None:
    baseline_root = tmp_path / "project"
    workspace = baseline_root / "workspaces" / "model-agent" / "case-demo"
    relative = Path("src/eventrelay/config.py")
    correct = "return True\n"
    for root in (baseline_root, workspace):
        (root / relative).parent.mkdir(parents=True)
        (root / relative).write_text(correct, encoding="utf-8")
    trace = _successful_trace(workspace, "different content\n")

    with pytest.raises(DemoEvidenceError, match="digest"):
        build_patch_preview(
            trace,
            {"file": relative.as_posix(), "find": "return True", "replace": "return False"},
            baseline_root,
        )


def test_verification_and_failure_summaries_expose_only_control_outcomes(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    verification = build_verification_summary(_successful_trace(workspace, "content"))
    assert verification["policy"]["ok"] is True
    assert verification["target"] == {
        "ok": True,
        "detail": "registered target test passed",
        "durationMs": 12,
        "errorCode": None,
    }
    trace = ShowcaseTrace(
        task_id="model-agent-failure",
        case_id="05",
        issue="issue",
        status="needs_human",
        agent_version="0.3.0",
        model="fake",
        events=(
            ("deterministic_recovery", {"raw": "must-not-appear"}),
            ("model_plan_recorded", {"kind": "invalid", "policy_accepted": False}),
            (
                "status_changed",
                {
                    "from": "running",
                    "to": "needs_human",
                    "reason": "planner stopped safely: model proposed an invalid patch",
                },
            ),
        ),
    )
    failure = build_failure_control_summary(trace)
    assert failure == {
        "stopReason": "planner stopped safely: model proposed an invalid patch",
        "policyRejected": True,
        "deterministicRecoveries": 1,
        "patchAttempted": False,
        "patchApplied": False,
        "errorCode": None,
        "testsStarted": False,
    }
