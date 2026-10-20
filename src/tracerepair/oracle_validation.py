"""Fail-closed oracle checks for pinned historical Python repair tasks."""

from __future__ import annotations

import hashlib
import shutil
import stat
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from uuid import uuid4

from tracerepair.benchmark_suite import BenchmarkManifest, BenchmarkTask
from tracerepair.repository_task import RepositoryTaskSpec, materialize_repository
from tracerepair.test_runner import RestrictedTestRunner, TestRunResult


class OracleValidationError(RuntimeError):
    """The benchmark cannot distinguish the historical bug from infrastructure failure."""


@dataclass(frozen=True)
class OracleResult:
    task_id: str
    buggy_exit_code: int
    fixed_target_passed: bool
    fixed_regression_passed: bool


_FIXED_ARCHIVES = {
    "c2c410c1521a3b1eb3efef52f3b06c2e42f7b92b": (
        "humanize-c2c410c.zip",
        "64401a4d166931f8add684cf23ace1baa10ac0d3796392bf8940e35eb333a93e",
    ),
    "435774ef8b10c1355bf77483a837945034011754": (
        "boltons-435774e.zip",
        "50cfc157b79e876e91f2408d2283acedd7f0940cbe1869599cb9aabf6c1c951f",
    ),
    "67fcf640477c78605580f5ee703a54c73c1e7a8a": (
        "more-itertools-67fcf64.zip",
        "82671a4c72d0cc55a50860257d1547a00bb9fb2d5eee6f1853b2901c92ca0a5f",
    ),
}


def validate_historical_oracles(
    manifest: BenchmarkManifest,
    tasks: tuple[BenchmarkTask, ...],
    project_root: Path,
) -> tuple[OracleResult, ...]:
    """Validate buggy-fails/fixed-passes before any provider request is made."""

    root = project_root.resolve()
    temporary_root = root / ".tmp" / f"oracle-preflight-{uuid4().hex}"
    results: list[OracleResult] = []
    try:
        for task in tasks:
            spec = RepositoryTaskSpec.load(task.config_path)
            task_root = temporary_root / task.task_id
            buggy = materialize_repository(spec, task_root / "buggy")
            archive = _fixed_archive(root, task)
            extracted = task_root / "fixed-extracted"
            _safe_extract(archive, extracted)
            fixed = _single_top_directory(extracted)
            _write_generated_files(task.task_id, fixed)
            fixed_spec = replace(spec, repository_root=fixed)
            fixed_spec.validate_repository()
            results.append(validate_oracle_pair(task.task_id, spec, buggy, fixed_spec, fixed))
    finally:
        if temporary_root.exists() and temporary_root.is_relative_to(root / ".tmp"):
            shutil.rmtree(temporary_root, ignore_errors=True)
    return tuple(results)


def validate_oracle_pair(
    task_id: str,
    spec: RepositoryTaskSpec,
    buggy: Path,
    fixed_spec: RepositoryTaskSpec,
    fixed: Path,
) -> OracleResult:
    buggy_result = _runner(spec, buggy).run_tests(spec.target_test)
    if buggy_result.ok or buggy_result.exit_code != 1 or buggy_result.timed_out:
        raise OracleValidationError(
            f"{task_id}: buggy target must fail with pytest exit code 1; "
            f"got {_outcome(buggy_result)}"
        )
    fixed_runner = _runner(fixed_spec, fixed)
    fixed_target = fixed_runner.run_tests(fixed_spec.target_test)
    if not fixed_target.ok:
        raise OracleValidationError(
            f"{task_id}: fixed target did not pass; got {_outcome(fixed_target)}"
        )
    fixed_regression = fixed_runner.run_regression()
    if not fixed_regression.ok:
        raise OracleValidationError(
            f"{task_id}: fixed regression did not pass; got {_outcome(fixed_regression)}"
        )
    return OracleResult(task_id, buggy_result.exit_code, True, True)


def _runner(spec: RepositoryTaskSpec, root: Path) -> RestrictedTestRunner:
    return RestrictedTestRunner(
        root,
        allowed_targets=(spec.target_test,),
        regression_selector=spec.regression_suite,
        pythonpath=spec.pythonpath,
        timeout_seconds=spec.timeout_seconds,
    )


def _fixed_archive(project_root: Path, task: BenchmarkTask) -> Path:
    configured = _FIXED_ARCHIVES.get(task.source.fixed_commit)
    if configured is None:
        raise OracleValidationError(
            f"{task.task_id}: fixed commit has no pinned oracle archive"
        )
    filename, expected = configured
    path = project_root / "evaluation" / "archives" / filename
    if not path.is_file():
        raise OracleValidationError(f"{task.task_id}: fixed oracle archive is missing")
    if _file_sha256(path) != expected:
        raise OracleValidationError(f"{task.task_id}: fixed oracle archive checksum mismatch")
    return path


def _safe_extract(path: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            member = PurePosixPath(info.filename)
            mode = info.external_attr >> 16
            if member.is_absolute() or ".." in member.parts or not member.parts or stat.S_ISLNK(mode):
                raise OracleValidationError(f"unsafe member in fixed oracle archive: {path.name}")
            target = destination.joinpath(*member.parts).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise OracleValidationError(f"fixed oracle archive escapes destination: {path.name}")
        archive.extractall(destination)


def _single_top_directory(path: Path) -> Path:
    children = [child for child in path.iterdir() if child.is_dir()]
    if len(children) != 1 or any(child.is_file() for child in path.iterdir()):
        raise OracleValidationError("fixed oracle archive must contain one top-level directory")
    return children[0]


def _write_generated_files(task_id: str, root: Path) -> None:
    if task_id != "humanize-negative-fraction":
        return
    target = root / "src" / "humanize" / "_version.py"
    target.write_text(
        '"""Deterministic version stub for the source-archive benchmark fixture."""\n\n'
        '__version__ = "0+tracerepair-benchmark"\n',
        encoding="utf-8",
        newline="\n",
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _outcome(result: TestRunResult) -> str:
    return (
        f"exit_code={result.exit_code}, timed_out={result.timed_out}, "
        f"error_code={result.error_code}"
    )
