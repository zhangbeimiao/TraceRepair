"""Render a safe, human-readable view of one persisted repair trace."""

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ShowcaseTrace:
    task_id: str
    case_id: str
    issue: str
    status: str
    agent_version: str
    model: str
    events: tuple[tuple[str, dict[str, object]], ...]
    workspace: str = ""


def load_showcase_trace(database: Path, task_id: str | None = None) -> ShowcaseTrace:
    if not database.is_file():
        raise FileNotFoundError(database)
    uri = database.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        if task_id is None:
            task = connection.execute(
                """SELECT task_id, case_id, issue, workspace, status FROM tasks
                WHERE task_id LIKE 'model-agent-%'
                ORDER BY updated_at DESC LIMIT 1"""
            ).fetchone()
        else:
            task = connection.execute(
                "SELECT task_id, case_id, issue, workspace, status FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        if task is None:
            raise KeyError(f"unknown task: {task_id or 'latest'}")
        rows = connection.execute(
            "SELECT event_type, payload_json FROM trace_events WHERE task_id = ? ORDER BY sequence",
            (task["task_id"],),
        ).fetchall()
    finally:
        connection.close()
    events = tuple((row["event_type"], json.loads(row["payload_json"])) for row in rows)
    metadata = next((payload for kind, payload in events if kind == "run_metadata"), {})
    return ShowcaseTrace(
        task_id=str(task["task_id"]),
        case_id=str(task["case_id"]),
        issue=str(task["issue"]),
        status=str(task["status"]),
        agent_version=str(metadata.get("agent_version", "legacy")),
        model=str(metadata.get("model", "unknown")),
        events=events,
        workspace=str(task["workspace"]),
    )


def showcase_steps(trace: ShowcaseTrace) -> tuple[str, ...]:
    steps: list[str] = []
    for kind, payload in trace.events:
        detail: str | None = None
        if kind == "workflow_phase_changed":
            detail = f"phase -> {payload.get('phase')}"
        elif kind == "model_plan_recorded":
            plan_kind = payload.get("kind")
            selected = payload.get("tool") or plan_kind
            detail = (
                f"model -> {selected}; tokens={payload.get('completion_tokens', 0)}; "
                f"policy_accepted={payload.get('policy_accepted')}"
            )
        elif kind == "tool_finished":
            summary = payload.get("summary", {})
            if not isinstance(summary, dict):
                summary = {}
            safe_bits = []
            for key in ("hit_count", "paths", "path", "files", "exit_code", "duration_ms"):
                if key in summary:
                    safe_bits.append(f"{key}={summary[key]}")
            suffix = "; ".join(safe_bits) or f"error_code={payload.get('error_code')}"
            detail = f"tool {payload.get('tool')} -> ok={payload.get('ok')}; {suffix}"
        elif kind == "status_changed":
            detail = (
                f"state {payload.get('from')} -> {payload.get('to')}; "
                f"reason={payload.get('reason')}"
            )
        elif kind == "deterministic_recovery":
            detail = "controller -> deterministic recovery"
        if detail is not None:
            steps.append(detail)
    return tuple(steps)


def render_showcase(trace: ShowcaseTrace) -> str:
    lines = [
        "TraceRepair - auditable repair run",
        "=" * 40,
        f"Task:    {trace.task_id}",
        f"Case:    {trace.case_id}",
        f"Issue:   {trace.issue}",
        f"Agent:   {trace.agent_version} ({trace.model})",
        "",
        "Execution timeline",
        "-" * 40,
    ]
    lines.extend(
        f"{index:02d}. {detail}" for index, detail in enumerate(showcase_steps(trace), start=1)
    )
    lines.extend(
        [
            "",
            f"Final status: {trace.status}",
            "Safety: no API key, raw model response, source body, test output, or diff is displayed.",
        ]
    )
    return "\n".join(lines)
