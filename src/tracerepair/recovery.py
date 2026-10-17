"""Durable, integrity-checked checkpoints for end-to-end repair recovery."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from tracerepair.models import TaskStatus
from tracerepair.read_tools import FileSlice
from tracerepair.store import TraceStore


SOURCE_READ = "source_read"
PATCH_APPLIED = "patch_applied"
TARGET_PASSED = "target_passed"
RECOVERY_SCHEMA_VERSION = 1


class RecoveryError(RuntimeError):
    """Raised when a persisted checkpoint cannot be resumed safely."""


class InjectedCrash(RuntimeError):
    """A deliberate interruption used to prove restart behavior."""

    def __init__(self, point: str) -> None:
        super().__init__(f"injected crash after {point}")
        self.point = point


def save_source_checkpoint(
    task_id: str,
    store: TraceStore,
    workspace: Path,
    source: FileSlice,
    *,
    diagnosis_turns: int,
) -> None:
    """Persist the source slice outside SQLite and record only hashes in the trace."""

    workspace = workspace.resolve()
    artifact_dir = (workspace / ".tracerepair" / "checkpoints").resolve()
    if not artifact_dir.is_relative_to(workspace):
        raise RecoveryError("checkpoint directory escaped the task workspace")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact = artifact_dir / "diagnosed-source.json"
    payload = {
        "schema_version": RECOVERY_SCHEMA_VERSION,
        "path": source.path,
        "start_line": source.start_line,
        "end_line": source.end_line,
        "content": source.content,
    }
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    temporary = artifact.with_suffix(".tmp")
    temporary.write_bytes(encoded)
    temporary.replace(artifact)
    relative_artifact = artifact.relative_to(workspace).as_posix()
    _save_recovery_state(
        task_id,
        store,
        {
            "schema_version": RECOVERY_SCHEMA_VERSION,
            "phase": SOURCE_READ,
            "source_artifact": relative_artifact,
            "source_artifact_sha256": _digest_bytes(encoded),
            "source_content_sha256": _digest_text(source.content),
            "source_path": source.path,
            "diagnosis_turns": diagnosis_turns,
        },
    )


def load_source_checkpoint(
    task_id: str, store: TraceStore, workspace: Path
) -> tuple[FileSlice, int]:
    """Restore a source slice after verifying the artifact and current file contents."""

    state = recovery_state(store.load_checkpoint(task_id))
    if state.get("phase") != SOURCE_READ:
        raise RecoveryError("source checkpoint is not the active recovery phase")
    workspace = workspace.resolve()
    relative = state.get("source_artifact")
    if not isinstance(relative, str) or not relative.startswith(".tracerepair/checkpoints/"):
        raise RecoveryError("source checkpoint artifact path is invalid")
    artifact = (workspace / relative).resolve()
    if not artifact.is_relative_to(workspace) or not artifact.is_file():
        raise RecoveryError("source checkpoint artifact is unavailable")
    encoded = artifact.read_bytes()
    if _digest_bytes(encoded) != state.get("source_artifact_sha256"):
        raise RecoveryError("source checkpoint artifact failed integrity verification")
    try:
        payload = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RecoveryError("source checkpoint artifact is malformed") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != RECOVERY_SCHEMA_VERSION:
        raise RecoveryError("source checkpoint schema is unsupported")
    path = payload.get("path")
    content = payload.get("content")
    start_line = payload.get("start_line")
    end_line = payload.get("end_line")
    if (
        not isinstance(path, str)
        or not path.startswith("src/eventrelay/")
        or not isinstance(content, str)
        or not isinstance(start_line, int)
        or not isinstance(end_line, int)
    ):
        raise RecoveryError("source checkpoint fields are invalid")
    if _digest_text(content) != state.get("source_content_sha256"):
        raise RecoveryError("source checkpoint content hash changed")
    source_path = (workspace / path).resolve()
    if not source_path.is_relative_to(workspace) or not source_path.is_file():
        raise RecoveryError("checkpoint source path is unavailable")
    current_lines = source_path.read_text(encoding="utf-8").splitlines(keepends=True)
    current_slice = "".join(current_lines[start_line - 1 : end_line])
    if current_slice != content:
        raise RecoveryError("workspace source changed after the checkpoint")
    turns = state.get("diagnosis_turns")
    if not isinstance(turns, int) or not 1 <= turns <= 5:
        raise RecoveryError("checkpoint diagnosis turn count is invalid")
    return FileSlice(path, start_line, end_line, content), turns


def mark_recovery_phase(
    task_id: str,
    store: TraceStore,
    phase: str,
    *,
    details: Mapping[str, object] | None = None,
) -> None:
    if phase not in {PATCH_APPLIED, TARGET_PASSED}:
        raise ValueError(f"unsupported recovery phase: {phase}")
    current = recovery_state(store.load_checkpoint(task_id))
    state: dict[str, object] = dict(current)
    state.update({"schema_version": RECOVERY_SCHEMA_VERSION, "phase": phase})
    if details:
        state.update(details)
    _save_recovery_state(task_id, store, state)


def recovery_state(checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    state = checkpoint.get("recovery", {})
    if not isinstance(state, dict):
        raise RecoveryError("recovery checkpoint is malformed")
    return dict(state)


def inject_crash_if_requested(
    task_id: str,
    store: TraceStore,
    *,
    configured_point: str | None,
    reached_point: str,
) -> None:
    """Interrupt immediately after a durable checkpoint has been committed."""

    if configured_point != reached_point:
        return
    store.append_event(task_id, "crash_injected", {"point": reached_point})
    if store.get_task(task_id).status is TaskStatus.RUNNING:
        store.transition(task_id, TaskStatus.INTERRUPTED, f"injected crash after {reached_point}")
    raise InjectedCrash(reached_point)


def _save_recovery_state(
    task_id: str, store: TraceStore, state: Mapping[str, object]
) -> None:
    checkpoint = store.load_checkpoint(task_id)
    checkpoint["recovery"] = dict(state)
    store.save_checkpoint(task_id, checkpoint)
    store.append_event(
        task_id,
        "recovery_checkpoint_saved",
        {
            "phase": state["phase"],
            "schema_version": RECOVERY_SCHEMA_VERSION,
        },
    )


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest_text(value: str) -> str:
    return _digest_bytes(value.encode("utf-8"))
