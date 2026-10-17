"""Validated configuration and disposable workspaces for external Python repositories."""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


SCHEMA_VERSION = 1
DEFAULT_MAX_REPOSITORY_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_REPOSITORY_FILES = 2_000
_TASK_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}$")
_PYTEST_SELECTOR = re.compile(
    r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.py"
    r"(?:::[A-Za-z_][A-Za-z0-9_]*(?:\[[A-Za-z0-9_.-]+\])?)*$"
)
_REGRESSION_SELECTOR = re.compile(
    r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*(?:\.py)?$"
)
_IGNORED_NAMES = {
    ".git",
    ".tracerepair",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "node_modules",
    "venv",
}


class RepositoryTaskError(ValueError):
    """A fail-closed configuration or materialisation error."""


@dataclass(frozen=True)
class RepositoryTaskSpec:
    """All repository-specific boundaries required by the generic repair workflow."""

    name: str
    repository_root: Path
    issue: str
    source_allowlist: tuple[str, ...]
    target_test: str
    regression_suite: str
    diagnostic_queries: tuple[str, ...]
    pythonpath: tuple[str, ...] = ("src",)
    timeout_seconds: int = 30
    max_repository_bytes: int = DEFAULT_MAX_REPOSITORY_BYTES
    max_repository_files: int = DEFAULT_MAX_REPOSITORY_FILES

    @classmethod
    def load(cls, path: Path) -> "RepositoryTaskSpec":
        config_path = path.resolve()
        if not config_path.is_file():
            raise RepositoryTaskError(f"task config does not exist: {path}")
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RepositoryTaskError("task config is not valid UTF-8 JSON") from error
        if not isinstance(payload, dict):
            raise RepositoryTaskError("task config root must be an object")
        return cls.from_mapping(payload, base_directory=config_path.parent)

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        base_directory: Path | None = None,
        validate_repository: bool = True,
    ) -> "RepositoryTaskSpec":
        if payload.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
            raise RepositoryTaskError("unsupported repository task schema_version")
        raw_root = payload.get("repository_root")
        if not isinstance(raw_root, str) or not raw_root.strip():
            raise RepositoryTaskError("repository_root must be a non-empty string")
        root = Path(raw_root)
        if not root.is_absolute():
            if base_directory is None:
                raise RepositoryTaskError("relative repository_root requires a config directory")
            root = base_directory / root
        root = root.resolve()

        name = _required_text(payload, "name", maximum=50)
        if not _TASK_NAME.fullmatch(name):
            raise RepositoryTaskError("name must be a lowercase, hyphenated identifier")
        issue = _required_text(payload, "issue", maximum=2_000)
        source_allowlist = _relative_list(payload, "source_allowlist", minimum=1, maximum=12)
        target_test = _required_text(payload, "target_test", maximum=300)
        regression_suite = _required_text(payload, "regression_suite", maximum=200)
        diagnostic_queries = _text_list(payload, "diagnostic_queries", minimum=1, maximum=8)
        pythonpath = _relative_list(
            payload,
            "pythonpath",
            minimum=1,
            maximum=8,
            default=("src",),
            allow_current=True,
        )
        timeout_seconds = _bounded_integer(payload, "timeout_seconds", 30, 1, 120)
        max_bytes = _bounded_integer(
            payload,
            "max_repository_bytes",
            DEFAULT_MAX_REPOSITORY_BYTES,
            1,
            200 * 1024 * 1024,
        )
        max_files = _bounded_integer(
            payload,
            "max_repository_files",
            DEFAULT_MAX_REPOSITORY_FILES,
            1,
            10_000,
        )
        if not _PYTEST_SELECTOR.fullmatch(target_test):
            raise RepositoryTaskError("target_test is not a bounded pytest node selector")
        if not _REGRESSION_SELECTOR.fullmatch(regression_suite):
            raise RepositoryTaskError("regression_suite must be one relative file or directory")

        spec = cls(
            name=name,
            repository_root=root,
            issue=issue,
            source_allowlist=source_allowlist,
            target_test=target_test,
            regression_suite=regression_suite,
            diagnostic_queries=diagnostic_queries,
            pythonpath=pythonpath,
            timeout_seconds=timeout_seconds,
            max_repository_bytes=max_bytes,
            max_repository_files=max_files,
        )
        if validate_repository:
            spec.validate_repository()
        return spec

    def validate_repository(self) -> None:
        if not self.repository_root.is_dir():
            raise RepositoryTaskError(f"repository_root is not a directory: {self.repository_root}")
        if os.name == "nt" and self.repository_root.drive.casefold() == "c:":
            raise RepositoryTaskError("repository_root must not use C: on this workstation")
        for relative in self.source_allowlist + self.pythonpath:
            target = _resolve_inside(self.repository_root, relative)
            if not target.is_dir():
                raise RepositoryTaskError(f"configured directory does not exist: {relative}")
        for relative in self.source_allowlist:
            first = PurePosixPath(relative).parts[0].casefold()
            if first in {"test", "tests", ".github"}:
                raise RepositoryTaskError("source_allowlist may not include tests or workflow files")
        target_file = _resolve_inside(self.repository_root, self.target_test.split("::", 1)[0])
        if not target_file.is_file():
            raise RepositoryTaskError("target_test file does not exist")
        regression = _resolve_inside(self.repository_root, self.regression_suite)
        if not regression.exists():
            raise RepositoryTaskError("regression_suite does not exist")
        if not any((self.repository_root / name).is_file() for name in ("pytest.ini", "pyproject.toml")):
            raise RepositoryTaskError("repository must contain pytest.ini or pyproject.toml")
        _repository_inventory(
            self.repository_root,
            max_files=self.max_repository_files,
            max_bytes=self.max_repository_bytes,
        )

    def runtime_payload(self) -> dict[str, object]:
        """Return checkpoint-safe boundaries needed after a process restart."""

        return {
            "schema_version": SCHEMA_VERSION,
            "name": self.name,
            "source_allowlist": list(self.source_allowlist),
            "target_test": self.target_test,
            "regression_suite": self.regression_suite,
            "diagnostic_queries": list(self.diagnostic_queries),
            "pythonpath": list(self.pythonpath),
            "timeout_seconds": self.timeout_seconds,
            "max_repository_bytes": self.max_repository_bytes,
            "max_repository_files": self.max_repository_files,
        }


def materialize_repository(spec: RepositoryTaskSpec, destination: Path) -> Path:
    """Copy a validated repository into one disposable, bounded workspace."""

    spec.validate_repository()
    destination = destination.resolve()
    if os.name == "nt" and destination.drive.casefold() == "c:":
        raise RepositoryTaskError("workspace destination must not use C: on this workstation")
    if destination.exists():
        raise RepositoryTaskError(f"workspace already exists: {destination}")
    inventory = _repository_inventory(
        spec.repository_root,
        max_files=spec.max_repository_files,
        max_bytes=spec.max_repository_bytes,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()
    try:
        for relative in inventory:
            source = spec.repository_root / relative
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    except OSError as error:
        shutil.rmtree(destination, ignore_errors=True)
        raise RepositoryTaskError("failed to materialize disposable repository workspace") from error
    return destination


def runtime_spec(payload: Mapping[str, Any], workspace: Path, issue: str) -> RepositoryTaskSpec:
    """Rebuild trusted runtime boundaries stored in the checkpoint for resume."""

    hydrated = dict(payload)
    hydrated["repository_root"] = str(workspace.resolve())
    hydrated["issue"] = issue
    return RepositoryTaskSpec.from_mapping(hydrated, validate_repository=True)


def is_allowed_source_path(path: str, roots: tuple[str, ...]) -> bool:
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts or candidate.suffix != ".py":
        return False
    return any(candidate == PurePosixPath(root) or PurePosixPath(root) in candidate.parents for root in roots)


def _repository_inventory(root: Path, *, max_files: int, max_bytes: int) -> tuple[Path, ...]:
    files: list[Path] = []
    total_bytes = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in _IGNORED_NAMES for part in relative.parts):
            continue
        if path.is_symlink():
            raise RepositoryTaskError(f"symbolic links are not supported: {relative.as_posix()}")
        if not path.is_file():
            continue
        files.append(relative)
        if len(files) > max_files:
            raise RepositoryTaskError("repository exceeds max_repository_files")
        try:
            total_bytes += path.stat().st_size
        except OSError as error:
            raise RepositoryTaskError("repository inventory could not be read") from error
        if total_bytes > max_bytes:
            raise RepositoryTaskError("repository exceeds max_repository_bytes")
    if not files:
        raise RepositoryTaskError("repository contains no materializable files")
    return tuple(files)


def _resolve_inside(root: Path, relative: str) -> Path:
    target = (root / Path(relative)).resolve()
    if not target.is_relative_to(root.resolve()):
        raise RepositoryTaskError(f"path escapes repository_root: {relative}")
    return target


def _required_text(payload: Mapping[str, Any], key: str, *, maximum: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise RepositoryTaskError(f"{key} must be a non-empty string up to {maximum} characters")
    return value.strip()


def _text_list(
    payload: Mapping[str, Any], key: str, *, minimum: int, maximum: int
) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise RepositoryTaskError(f"{key} must contain between {minimum} and {maximum} strings")
    if any(not isinstance(item, str) or not 2 <= len(item) <= 200 for item in value):
        raise RepositoryTaskError(f"{key} contains an invalid string")
    return tuple(dict.fromkeys(item.strip() for item in value))


def _relative_list(
    payload: Mapping[str, Any],
    key: str,
    *,
    minimum: int,
    maximum: int,
    default: tuple[str, ...] | None = None,
    allow_current: bool = False,
) -> tuple[str, ...]:
    raw = payload.get(key, list(default) if default is not None else None)
    if not isinstance(raw, list) or not minimum <= len(raw) <= maximum:
        raise RepositoryTaskError(f"{key} must contain between {minimum} and {maximum} paths")
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise RepositoryTaskError(f"{key} contains a non-string path")
        path = PurePosixPath(item.replace("\\", "/"))
        if str(path) == "." and allow_current:
            values.append(".")
            continue
        if (
            path.is_absolute()
            or ".." in path.parts
            or not path.parts
            or str(path) in {".", ""}
            or any(":" in part for part in path.parts)
        ):
            raise RepositoryTaskError(f"{key} contains an unsafe path")
        values.append(path.as_posix())
    return tuple(dict.fromkeys(values))


def _bounded_integer(
    payload: Mapping[str, Any], key: str, default: int, minimum: int, maximum: int
) -> int:
    value = payload.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise RepositoryTaskError(f"{key} must be between {minimum} and {maximum}")
    return value
