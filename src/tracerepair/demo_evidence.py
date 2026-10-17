"""Build public demo evidence from private workspaces and sanitized trace metadata."""

from __future__ import annotations

import hashlib
from difflib import unified_diff
from pathlib import Path
from typing import Mapping

from tracerepair.showcase import ShowcaseTrace


class DemoEvidenceError(ValueError):
    """Raised when public evidence cannot be tied back to a recorded run."""


def build_patch_preview(
    trace: ShowcaseTrace,
    case: Mapping[str, object],
    baseline_root: Path,
) -> dict[str, object]:
    """Reconstruct the applied change and verify it against the recorded file digest."""

    relative_path = str(case.get("file", ""))
    if not relative_path.startswith("src/eventrelay/"):
        raise DemoEvidenceError("patch preview is restricted to EventRelay source files")
    if not trace.workspace:
        raise DemoEvidenceError("trace does not record a disposable workspace")

    baseline_root = baseline_root.resolve()
    baseline_path = (baseline_root / relative_path).resolve()
    workspace_root = Path(trace.workspace).resolve()
    allowed_workspaces = (baseline_root / "workspaces" / "model-agent").resolve()
    repaired_path = (workspace_root / relative_path).resolve()
    if not baseline_path.is_relative_to(baseline_root):
        raise DemoEvidenceError("baseline path escaped the project root")
    if not workspace_root.is_relative_to(allowed_workspaces):
        raise DemoEvidenceError("trace workspace is outside the model-agent workspace root")
    if not repaired_path.is_relative_to(workspace_root):
        raise DemoEvidenceError("workspace path escaped the disposable workspace")
    if not baseline_path.is_file() or not repaired_path.is_file():
        raise DemoEvidenceError("patch preview source file is missing")

    baseline = baseline_path.read_text(encoding="utf-8")
    find = str(case.get("find", ""))
    replacement = str(case.get("replace", ""))
    if not find or baseline.count(find) != 1:
        raise DemoEvidenceError("benchmark fault transformation is not unique")
    faulty = baseline.replace(find, replacement, 1)
    repaired = repaired_path.read_text(encoding="utf-8")

    applied = _tool_result(trace, "apply_patch", require_ok=True)
    summary = applied.get("summary", {})
    if not isinstance(summary, dict):
        raise DemoEvidenceError("apply_patch summary is malformed")
    files = summary.get("files", [])
    hashes = summary.get("file_sha256", {})
    if relative_path not in files or not isinstance(hashes, dict):
        raise DemoEvidenceError("recorded patch did not modify the benchmark target")
    recorded_hash = str(hashes.get(relative_path, ""))
    content_hash = hashlib.sha256(repaired.encode("utf-8")).hexdigest()
    if not recorded_hash or recorded_hash != content_hash:
        raise DemoEvidenceError("repaired file does not match the recorded trace digest")

    raw_lines = list(
        unified_diff(
            faulty.splitlines(),
            repaired.splitlines(),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
            lineterm="",
            n=3,
        )
    )
    if not raw_lines:
        raise DemoEvidenceError("verified workspace contains no change")
    lines = [{"kind": _diff_kind(line, index), "text": line} for index, line in enumerate(raw_lines)]
    started = _tool_started(trace, "apply_patch")
    arguments = started.get("arguments", {})
    diff_hash = str(arguments.get("diff_sha256", "")) if isinstance(arguments, dict) else ""
    return {
        "file": relative_path,
        "lines": lines,
        "addedLines": sum(line["kind"] == "added" for line in lines),
        "removedLines": sum(line["kind"] == "removed" for line in lines),
        "diffSha256": diff_hash,
        "contentSha256": content_hash,
        "evidence": "reconstructed from the faulty snapshot and SHA-256 verified workspace",
    }


def build_verification_summary(trace: ShowcaseTrace) -> dict[str, object]:
    """Return the four gates that decide whether a model patch may reach review."""

    patch_plans = [
        payload
        for kind, payload in trace.events
        if kind == "model_plan_recorded" and payload.get("kind") == "patch"
    ]
    final_changes = [payload for kind, payload in trace.events if kind == "status_changed"]
    return {
        "policy": {
            "ok": any(plan.get("policy_accepted") is True for plan in patch_plans),
            "detail": "model patch accepted as a candidate; deterministic policy still applies",
        },
        "apply": _public_tool_gate(trace, "apply_patch", "candidate written to disposable copy"),
        "target": _public_tool_gate(trace, "run_tests", "registered target test passed"),
        "regression": _public_tool_gate(
            trace, "run_regression", "complete EventRelay regression passed"
        ),
        "finalReason": str(final_changes[-1].get("reason", "unknown")) if final_changes else "unknown",
    }


def build_failure_control_summary(trace: ShowcaseTrace) -> dict[str, object]:
    """Describe why a failed run stopped without exposing raw model output."""

    status_changes = [payload for kind, payload in trace.events if kind == "status_changed"]
    plans = [payload for kind, payload in trace.events if kind == "model_plan_recorded"]
    tools = [payload for kind, payload in trace.events if kind == "tool_finished"]
    starts = [payload for kind, payload in trace.events if kind == "tool_started"]
    patch_result = next((item for item in tools if item.get("tool") == "apply_patch"), None)
    return {
        "stopReason": str(status_changes[-1].get("reason", "unknown"))
        if status_changes
        else "unknown",
        "policyRejected": any(plan.get("policy_accepted") is False for plan in plans),
        "deterministicRecoveries": sum(
            kind == "deterministic_recovery" for kind, _ in trace.events
        ),
        "patchAttempted": any(item.get("tool") == "apply_patch" for item in starts),
        "patchApplied": bool(patch_result and patch_result.get("ok") is True),
        "errorCode": str(patch_result.get("error_code"))
        if patch_result and patch_result.get("error_code")
        else None,
        "testsStarted": any(
            item.get("tool") in {"run_tests", "run_regression"} for item in starts
        ),
    }


def _tool_result(
    trace: ShowcaseTrace, tool: str, *, require_ok: bool = False
) -> dict[str, object]:
    matches = [
        payload
        for kind, payload in trace.events
        if kind == "tool_finished"
        and payload.get("tool") == tool
        and (not require_ok or payload.get("ok") is True)
    ]
    if not matches:
        raise DemoEvidenceError(f"trace is missing a verified {tool} result")
    return matches[-1]


def _tool_started(trace: ShowcaseTrace, tool: str) -> dict[str, object]:
    matches = [
        payload
        for kind, payload in trace.events
        if kind == "tool_started" and payload.get("tool") == tool
    ]
    if not matches:
        raise DemoEvidenceError(f"trace is missing a {tool} start event")
    return matches[-1]


def _public_tool_gate(trace: ShowcaseTrace, tool: str, detail: str) -> dict[str, object]:
    try:
        payload = _tool_result(trace, tool)
    except DemoEvidenceError:
        return {"ok": False, "detail": "not executed", "durationMs": None, "errorCode": None}
    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    return {
        "ok": payload.get("ok") is True,
        "detail": detail if payload.get("ok") is True else "blocked before the next gate",
        "durationMs": summary.get("duration_ms"),
        "errorCode": payload.get("error_code"),
    }


def _diff_kind(line: str, index: int) -> str:
    if index < 2 or line.startswith("@@"):
        return "meta"
    if line.startswith("+"):
        return "added"
    if line.startswith("-"):
        return "removed"
    return "context"
