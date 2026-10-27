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
    "15555ed760000b049aff8fecc79d29339c1224c3": (
        "pysnooper-15555ed.zip",
        "0194d03bb6ffed0eef4410619d82f0280e7046bdf6e638e618f9c0e6ae3d0f05",
    ),
    "73962a47026dd980ac0758820efc9c41cbf938e0": (
        "tqdm-73962a4.zip",
        "c4be7c83d2b4c9a88a0a48b0277696625a5adf419578bf52ef3fd145fdf2d3ae",
    ),
    "c205683a8df8a57e2db1e9816a5a7ce3255b08fc": (
        "thefuck-c205683.zip",
        "2fd5475e3168ccfedd5aba25eb790c6c918e5d92dc4779e9169f8afe4c7d4710",
    ),
    "040d981f00c3f6830b2d0db3daf3c64c080e96e3": (
        "httpie-040d981.zip",
        "5207068009e5419b66c48a3cc030165860ddd3da9bbf6ee1b61128ae74a2b779",
    ),
    "1cc47c667419e0eadc0a6989256ab7b276852adf": (
        "youtube-dl-1cc47c6.zip",
        "33c711a4c3378e21304f567c4e31c0c4875f84fd51f6ede701c26f061a6cf063",
    ),
    "d2eba0374a452c2b18fe188b04527e22bda3548c": (
        "toolz-d2eba03.zip",
        "b647accf9b79fb4191c69e536411743ae1e3933b0614b480a8d17d1b4803d55e",
    ),
    "6ba75d41436d4400624c3e2f32727e127016b8c6": (
        "prettytable-6ba75d4.zip",
        "53a4797735581b2c5060db8b4f5349e200c68b88e8c3efd30b748c93c30bf263",
    ),
    "6fd41340f30519ddc64a546ad2703dfe53f12356": (
        "glom-6fd4134.zip",
        "369ed1500d35545807d549de9d3ec142ed70da6967947ea9694c9fd53ab21fe8",
    ),
    "ffe21c44d3f7de9c7a89870c8cf1fd7aa583a2ae": (
        "cachetools-ffe21c4.zip",
        "685f8c4374daea405b2f3466d85dca72be2f3b8d630be4f68be4eabbf4d3e980",
    ),
    "bc388221e3b48a0d33fc64090acb3985ba955fdf": (
        "python-slugify-bc38822.zip",
        "5b97082209fe2c549d42496349091113c9845d7d33c8b94e92c77134bf48bc7b",
    ),
    "f58ca3e81424a35626c8a475eb59ab95589008ce": (
        "click-f58ca3e.zip",
        "06bba4231892d2e82d7a9007dc01226d2c1eb778f5f49b6bea74e2b9b4bb0eab",
    ),
}


_PYSNOOPER_PY311_COMPAT = '''"""Benchmark-only compatibility for a dependency predating Python 3.11."""

import collections
import collections.abc
import inspect
from collections import namedtuple


for _name in (
    "Callable",
    "Container",
    "Hashable",
    "Iterable",
    "Iterator",
    "Mapping",
    "MutableMapping",
    "MutableSequence",
    "MutableSet",
    "Sequence",
    "Set",
    "Sized",
):
    if not hasattr(collections, _name):
        setattr(collections, _name, getattr(collections.abc, _name))

if not hasattr(inspect, "getargspec"):
    _ArgSpec = namedtuple("ArgSpec", "args varargs keywords defaults")

    def _getargspec(function):
        spec = inspect.getfullargspec(function)
        return _ArgSpec(spec.args, spec.varargs, spec.varkw, spec.defaults)

    inspect.getargspec = _getargspec
'''


_HTTPIE_REQUESTS_COMPAT = '''"""Benchmark-only compatibility for the historical Requests API."""

import sys

import requests.compat


if not hasattr(requests.compat, "is_windows"):
    requests.compat.is_windows = sys.platform.startswith("win")
if not hasattr(requests.compat, "is_py26"):
    requests.compat.is_py26 = False
'''


_HTTPIE_OFFLINE_ORACLE = '''"""Offline oracle for the historical lowercase Host-header regression."""

from types import SimpleNamespace

from requests.structures import CaseInsensitiveDict

from httpie.models import HTTPRequest


def _render(headers):
    request = SimpleNamespace(
        method="GET",
        url="http://127.0.0.1:8765/get",
        headers=CaseInsensitiveDict(headers),
        body=None,
    )
    return HTTPRequest(request).headers


def test_lowercase_host_is_not_duplicated():
    rendered = _render({"host": "example.test"})

    assert rendered.lower().count("host:") == 1
    assert "host: example.test" in rendered.lower()


def test_missing_host_uses_url_authority():
    rendered = _render({"Accept": "application/json"})

    assert rendered.lower().count("host:") == 1
    assert "host: 127.0.0.1:8765" in rendered.lower()
'''


_THEFUCK_PYTEST_COMPAT = '''"""Benchmark-only compatibility for the historical pytest Node API."""

from _pytest.nodes import Node


if not hasattr(Node, "get_marker"):
    Node.get_marker = Node.get_closest_marker
'''


_TOOLZ_INTERPOSE_ORACLE = '''"""Offline oracle for the historical empty-interpose regression."""

from toolz.itertoolz import interpose


def test_empty_sequence_returns_empty_iterator():
    assert list(interpose("separator", [])) == []
'''


_PRETTYTABLE_ALIGN_ORACLE = '''"""Offline oracle for the historical alignment getter regression."""

from prettytable import PrettyTable


def test_horizontal_align_getter_returns_configured_character():
    table = PrettyTable()
    table.horizontal_align_char = ":"

    assert table.horizontal_align_char == ":"


def test_default_horizontal_align_follows_junction_character():
    table = PrettyTable()
    table.junction_char = "#"

    assert table.horizontal_align_char == "#"
'''


_GLOM_PATH_ORACLE = '''"""Offline oracle for the historical Path index boundary regression."""

import pytest

from glom import Path


def test_index_equal_to_path_length_raises_index_error():
    path = Path("a", "b")

    with pytest.raises(IndexError):
        path[2]
'''


_CACHETOOLS_FALSEY_GETSIZEOF_ORACLE = '''"""Offline oracle for falsey getsizeof callables."""

from cachetools import Cache


class FalseyGetSize:
    def __bool__(self):
        return False

    def __call__(self, value):
        return len(value)


def test_falsey_getsizeof_callable_is_honored():
    cache = Cache(maxsize=10, getsizeof=FalseyGetSize())
    cache["key"] = "four"

    assert cache.currsize == 4


def test_default_getsizeof_still_counts_one_per_item():
    cache = Cache(maxsize=10)
    cache["key"] = "four"

    assert cache.currsize == 1
'''


def validate_historical_oracles(
    manifest: BenchmarkManifest,
    tasks: tuple[BenchmarkTask, ...],
    project_root: Path,
) -> tuple[OracleResult, ...]:
    """Validate buggy-fails/fixed-passes before any provider request is made."""

    root = project_root.resolve()
    temporary_root = root / ".tmp" / f"oracle-preflight-{uuid4().hex}"
    results: list[OracleResult] = []
    failures: list[str] = []
    try:
        for task in tasks:
            try:
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
                results.append(
                    validate_oracle_pair(task.task_id, spec, buggy, fixed_spec, fixed)
                )
            except OracleValidationError as error:
                failures.append(str(error))
    finally:
        if temporary_root.exists() and temporary_root.is_relative_to(root / ".tmp"):
            shutil.rmtree(temporary_root, ignore_errors=True)
    if failures:
        details = "\n".join(f"- {failure}" for failure in failures)
        raise OracleValidationError(f"oracle preflight failed for {len(failures)} task(s):\n{details}")
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
    if task_id == "humanize-negative-fraction":
        target = root / "src" / "humanize" / "_version.py"
        target.write_text(
            '"""Deterministic version stub for the source-archive benchmark fixture."""\n\n'
            '__version__ = "0+tracerepair-benchmark"\n',
            encoding="utf-8",
            newline="\n",
        )
    elif task_id == "pysnooper-file-output":
        (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8", newline="\n")
        (root / "conftest.py").write_text(
            _PYSNOOPER_PY311_COMPAT, encoding="utf-8", newline="\n"
        )
    elif task_id in {"httpie-host-header-case", "httpie-host-header-offline"}:
        (root / "conftest.py").write_text(
            _HTTPIE_REQUESTS_COMPAT, encoding="utf-8", newline="\n"
        )
        if task_id == "httpie-host-header-offline":
            target = root / "tests" / "test_tracerepair_host_header.py"
            target.write_text(_HTTPIE_OFFLINE_ORACLE, encoding="utf-8", newline="\n")
    elif task_id == "thefuck-git-push-match":
        (root / "conftest.py").write_text(
            _THEFUCK_PYTEST_COMPAT, encoding="utf-8", newline="\n"
        )
    elif task_id == "toolz-empty-interpose":
        target = root / "tests" / "test_tracerepair_interpose.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_TOOLZ_INTERPOSE_ORACLE, encoding="utf-8", newline="\n")
    elif task_id == "prettytable-horizontal-align":
        target = root / "tests" / "test_tracerepair_horizontal_align.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_PRETTYTABLE_ALIGN_ORACLE, encoding="utf-8", newline="\n")
        version = root / "src" / "prettytable" / "_version.py"
        version.write_text(
            '"""Deterministic version stub for the source-archive benchmark fixture."""\n\n'
            '__version__ = "0.0.0"\n',
            encoding="utf-8",
            newline="\n",
        )
    elif task_id == "glom-path-index-boundary":
        target = root / "glom" / "test" / "test_tracerepair_path_boundary.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_GLOM_PATH_ORACLE, encoding="utf-8", newline="\n")
    elif task_id == "cachetools-falsey-getsizeof":
        target = root / "tests" / "test_tracerepair_falsey_getsizeof.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            _CACHETOOLS_FALSEY_GETSIZEOF_ORACLE, encoding="utf-8", newline="\n"
        )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _outcome(result: TestRunResult) -> str:
    stdout = " ".join(result.stdout.split())[-1_600:]
    stderr = " ".join(result.stderr.split())[-1_600:]
    return (
        f"exit_code={result.exit_code}, timed_out={result.timed_out}, "
        f"error_code={result.error_code}, stdout={stdout!r}, stderr={stderr!r}"
    )
