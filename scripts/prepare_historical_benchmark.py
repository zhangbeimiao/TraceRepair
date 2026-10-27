"""Materialize pinned historical bug snapshots without executing repository code."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]


PYSNOOPER_PY311_COMPAT = '''"""Benchmark-only compatibility for a dependency predating Python 3.11."""

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


HTTPie_REQUESTS_COMPAT = '''"""Benchmark-only compatibility for the historical Requests API."""

import sys

import requests.compat


if not hasattr(requests.compat, "is_windows"):
    requests.compat.is_windows = sys.platform.startswith("win")
if not hasattr(requests.compat, "is_py26"):
    requests.compat.is_py26 = False
'''


HTTPIE_OFFLINE_ORACLE = '''"""Offline oracle for the historical lowercase Host-header regression."""

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


TOOLZ_INTERPOSE_ORACLE = '''"""Offline oracle for the historical empty-interpose regression."""

from toolz.itertoolz import interpose


def test_empty_sequence_returns_empty_iterator():
    assert list(interpose("separator", [])) == []
'''


PRETTYTABLE_ALIGN_ORACLE = '''"""Offline oracle for the historical alignment getter regression."""

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


GLOM_PATH_ORACLE = '''"""Offline oracle for the historical Path index boundary regression."""

import pytest

from glom import Path


def test_index_equal_to_path_length_raises_index_error():
    path = Path("a", "b")

    with pytest.raises(IndexError):
        path[2]
'''


CACHETOOLS_FALSEY_GETSIZEOF_ORACLE = '''"""Offline oracle for falsey getsizeof callables."""

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


THEFUCK_PYTEST_COMPAT = '''"""Benchmark-only compatibility for the historical pytest Node API."""

from _pytest.nodes import Node


if not hasattr(Node, "get_marker"):
    Node.get_marker = Node.get_closest_marker
'''


@dataclass(frozen=True)
class Archive:
    label: str
    owner: str
    repository: str
    commit: str
    sha256: str

    @property
    def filename(self) -> str:
        return f"{self.label}.zip"

    @property
    def url(self) -> str:
        return (
            f"https://codeload.github.com/{self.owner}/{self.repository}/zip/{self.commit}"
        )


@dataclass(frozen=True)
class HistoricalCase:
    name: str
    buggy: Archive
    fixed: Archive
    regression_test: str
    generated_files: tuple[tuple[str, str], ...] = ()


CASES = (
    HistoricalCase(
        "humanize-negative-fraction",
        Archive(
            "humanize-976484a",
            "python-humanize",
            "humanize",
            "976484a655df046aa6849f440a4f0cd44fc4918c",
            "eeaf4cd45f0a17e4f77c4c1bdf3c91dd522019031c5b180dcf1e3f33d2dee9b1",
        ),
        Archive(
            "humanize-c2c410c",
            "python-humanize",
            "humanize",
            "c2c410c1521a3b1eb3efef52f3b06c2e42f7b92b",
            "64401a4d166931f8add684cf23ace1baa10ac0d3796392bf8940e35eb333a93e",
        ),
        "tests/test_number.py",
        (
            (
                "src/humanize/_version.py",
                '"""Deterministic version stub for the source-archive benchmark fixture."""\n\n'
                '__version__ = "0+tracerepair-benchmark"\n',
            ),
        ),
    ),
    HistoricalCase(
        "boltons-empty-multireplace",
        Archive(
            "boltons-0a3084e",
            "mahmoud",
            "boltons",
            "0a3084e3058fd814684b1fc98343ec2e76d13ddc",
            "559b68ef022f0e0a28f54101b785dfd65096596fa3829c9c48a2fdcf2888bf35",
        ),
        Archive(
            "boltons-435774e",
            "mahmoud",
            "boltons",
            "435774ef8b10c1355bf77483a837945034011754",
            "50cfc157b79e876e91f2408d2283acedd7f0940cbe1869599cb9aabf6c1c951f",
        ),
        "tests/test_strutils.py",
    ),
    HistoricalCase(
        "more-itertools-falsey-validator",
        Archive(
            "more-itertools-1ea82a7",
            "more-itertools",
            "more-itertools",
            "1ea82a711c69f590054987b5cb194157f8ce8ac4",
            "a8de21bd320e514096104ba2095218d49a3c3961e2452e5c11f823c9a81b9d3c",
        ),
        Archive(
            "more-itertools-67fcf64",
            "more-itertools",
            "more-itertools",
            "67fcf640477c78605580f5ee703a54c73c1e7a8a",
            "82671a4c72d0cc55a50860257d1547a00bb9fb2d5eee6f1853b2901c92ca0a5f",
        ),
        "tests/test_more.py",
    ),
    HistoricalCase(
        "pysnooper-file-output",
        Archive(
            "pysnooper-6e3d797",
            "cool-RR",
            "PySnooper",
            "6e3d797be3fa0a746fb5b1b7c7fea78eb926c208",
            "14d47558c98530126e8362356a005282dbf41d97ba130d7405b0995f44549ec1",
        ),
        Archive(
            "pysnooper-15555ed",
            "cool-RR",
            "PySnooper",
            "15555ed760000b049aff8fecc79d29339c1224c3",
            "0194d03bb6ffed0eef4410619d82f0280e7046bdf6e638e618f9c0e6ae3d0f05",
        ),
        "tests/test_pysnooper.py",
        (
            ("pytest.ini", "[pytest]\n"),
            ("conftest.py", PYSNOOPER_PY311_COMPAT),
        ),
    ),
    HistoricalCase(
        "tqdm-sizeless-bool",
        Archive(
            "tqdm-c2599e3",
            "tqdm",
            "tqdm",
            "c2599e3cd6087429f48bae34347ec5d2473c8392",
            "3f64176c44689f835f81367ec0e0c7749c7b9484704e98805b8ce122e14bcc81",
        ),
        Archive(
            "tqdm-73962a4",
            "tqdm",
            "tqdm",
            "73962a47026dd980ac0758820efc9c41cbf938e0",
            "c4be7c83d2b4c9a88a0a48b0277696625a5adf419578bf52ef3fd145fdf2d3ae",
        ),
        "tqdm/tests/tests_tqdm.py",
    ),
    HistoricalCase(
        "thefuck-git-push-match",
        Archive(
            "thefuck-7c858fa",
            "nvbn",
            "thefuck",
            "7c858fadb3458be829d3d43666ccb46c3ed5b8a0",
            "5b68e9b17483f87f987e25a3a3a90f7e8543bd6cb7db935efe0637e839fa5f4f",
        ),
        Archive(
            "thefuck-c205683",
            "nvbn",
            "thefuck",
            "c205683a8df8a57e2db1e9816a5a7ce3255b08fc",
            "2fd5475e3168ccfedd5aba25eb790c6c918e5d92dc4779e9169f8afe4c7d4710",
        ),
        "tests/rules/test_git_push.py",
        (("conftest.py", THEFUCK_PYTEST_COMPAT),),
    ),
    HistoricalCase(
        "httpie-host-header-case",
        Archive(
            "httpie-8c892ed",
            "jakubroztocil",
            "httpie",
            "8c892edd4fe700a7ca5cc733dcb4817831d253e2",
            "dea581dbdeb02cb6f15301f21a1b15752b8b632fcb31fdabcce101c5626f4532",
        ),
        Archive(
            "httpie-040d981",
            "jakubroztocil",
            "httpie",
            "040d981f00c3f6830b2d0db3daf3c64c080e96e3",
            "5207068009e5419b66c48a3cc030165860ddd3da9bbf6ee1b61128ae74a2b779",
        ),
        "tests/test_regressions.py",
        (("conftest.py", HTTPie_REQUESTS_COMPAT),),
    ),
    HistoricalCase(
        "httpie-host-header-offline",
        Archive(
            "httpie-8c892ed",
            "jakubroztocil",
            "httpie",
            "8c892edd4fe700a7ca5cc733dcb4817831d253e2",
            "dea581dbdeb02cb6f15301f21a1b15752b8b632fcb31fdabcce101c5626f4532",
        ),
        Archive(
            "httpie-040d981",
            "jakubroztocil",
            "httpie",
            "040d981f00c3f6830b2d0db3daf3c64c080e96e3",
            "5207068009e5419b66c48a3cc030165860ddd3da9bbf6ee1b61128ae74a2b779",
        ),
        "tests/test_regressions.py",
        (
            ("conftest.py", HTTPie_REQUESTS_COMPAT),
            ("tests/test_tracerepair_host_header.py", HTTPIE_OFFLINE_ORACLE),
        ),
    ),
    HistoricalCase(
        "youtube-dl-boolean-filter",
        Archive(
            "youtube-dl-99036a1",
            "ytdl-org",
            "youtube-dl",
            "99036a1298089068dcf80c0985bfcc3f8c24f281",
            "7bce14549fb13d554d5a64938d45e4c7ea64cd6890c95cdaed77643ef198f452",
        ),
        Archive(
            "youtube-dl-1cc47c6",
            "ytdl-org",
            "youtube-dl",
            "1cc47c667419e0eadc0a6989256ab7b276852adf",
            "33c711a4c3378e21304f567c4e31c0c4875f84fd51f6ede701c26f061a6cf063",
        ),
        "test/test_utils.py",
    ),
    HistoricalCase(
        "toolz-empty-interpose",
        Archive(
            "toolz-55ce42d",
            "pytoolz",
            "toolz",
            "55ce42dc3b6f786ed9d4e38633cc5cfe3622a526",
            "003e33bc86212b761608f13023adae83ca84ec33f7c5a0b741e5c0573aa9d4e8",
        ),
        Archive(
            "toolz-d2eba03",
            "pytoolz",
            "toolz",
            "d2eba0374a452c2b18fe188b04527e22bda3548c",
            "b647accf9b79fb4191c69e536411743ae1e3933b0614b480a8d17d1b4803d55e",
        ),
        "toolz/tests/test_itertoolz.py",
        (("tests/test_tracerepair_interpose.py", TOOLZ_INTERPOSE_ORACLE),),
    ),
    HistoricalCase(
        "prettytable-horizontal-align",
        Archive(
            "prettytable-37a0266",
            "prettytable",
            "prettytable",
            "37a02661a7fab52d4d2db613ffeda44ea928ae60",
            "3bba4b6cc1a54c37bbd86cba8953033a0a3f1aeaf13497a74b96dc78c8afe515",
        ),
        Archive(
            "prettytable-6ba75d4",
            "prettytable",
            "prettytable",
            "6ba75d41436d4400624c3e2f32727e127016b8c6",
            "53a4797735581b2c5060db8b4f5349e200c68b88e8c3efd30b748c93c30bf263",
        ),
        "tests/test_prettytable.py",
        (
            ("tests/test_tracerepair_horizontal_align.py", PRETTYTABLE_ALIGN_ORACLE),
            (
                "src/prettytable/_version.py",
                '"""Deterministic version stub for the source-archive benchmark fixture."""\n\n'
                '__version__ = "0.0.0"\n',
            ),
        ),
    ),
    HistoricalCase(
        "glom-path-index-boundary",
        Archive(
            "glom-e515fb3",
            "mahmoud",
            "glom",
            "e515fb33c7af491c6a20b2618591736361bb1d08",
            "6a4f55e82706161dc648825e9b189e134f8990d59439f66c60553bc860e8fb53",
        ),
        Archive(
            "glom-6fd4134",
            "mahmoud",
            "glom",
            "6fd41340f30519ddc64a546ad2703dfe53f12356",
            "369ed1500d35545807d549de9d3ec142ed70da6967947ea9694c9fd53ab21fe8",
        ),
        "glom/test/test_path_and_t.py",
        (("glom/test/test_tracerepair_path_boundary.py", GLOM_PATH_ORACLE),),
    ),
    HistoricalCase(
        "cachetools-falsey-getsizeof",
        Archive(
            "cachetools-110fe5d",
            "tkem",
            "cachetools",
            "110fe5d03e7b4b8f5c5ec97533c94254cdf8733f",
            "2574dac474bc9f73b32b35d4ab6522bdf226946db31de4a571a62e07c10eab85",
        ),
        Archive(
            "cachetools-ffe21c4",
            "tkem",
            "cachetools",
            "ffe21c44d3f7de9c7a89870c8cf1fd7aa583a2ae",
            "685f8c4374daea405b2f3466d85dca72be2f3b8d630be4f68be4eabbf4d3e980",
        ),
        "tests/test_tracerepair_falsey_getsizeof.py",
        (("tests/test_tracerepair_falsey_getsizeof.py", CACHETOOLS_FALSEY_GETSIZEOF_ORACLE),),
    ),
    HistoricalCase(
        "python-slugify-invalid-types",
        Archive(
            "python-slugify-fee5aa3",
            "un33k",
            "python-slugify",
            "fee5aa338d3bd7a9e36c269e33b496a7848edc44",
            "6afc6a929730eac3da8ce34005762364c28ec55e02c5cf7037b0426e2138eca5",
        ),
        Archive(
            "python-slugify-bc38822",
            "un33k",
            "python-slugify",
            "bc388221e3b48a0d33fc64090acb3985ba955fdf",
            "5b97082209fe2c549d42496349091113c9845d7d33c8b94e92c77134bf48bc7b",
        ),
        "test.py",
    ),
    HistoricalCase(
        "click-sentinel-copy",
        Archive(
            "click-420c8fb",
            "pallets",
            "click",
            "420c8fb44eeadb537cae69d2fee3796e808558dd",
            "505860a5982cf7838cf790bafb7addaa26bd27a76e15fc3a380746d8ebe98203",
        ),
        Archive(
            "click-f58ca3e",
            "pallets",
            "click",
            "f58ca3e81424a35626c8a475eb59ab95589008ce",
            "06bba4231892d2e82d7a9007dc01226d2c1eb778f5f49b6bea74e2b9b4bb0eab",
        ),
        "tests/test_utils/test_sentinel.py",
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--download",
        action="store_true",
        help="download missing pinned archives; without this flag only cached archives are used",
    )
    arguments = parser.parse_args()
    if os.name == "nt" and ROOT.drive.casefold() != "d:":
        raise SystemExit("historical benchmark assets must remain on D: on this workstation")
    archive_root = ROOT / "evaluation" / "archives"
    repository_root = ROOT / "evaluation" / "repositories"
    archive_root.mkdir(parents=True, exist_ok=True)
    repository_root.mkdir(parents=True, exist_ok=True)
    required = {archive for case in CASES for archive in (case.buggy, case.fixed)}
    for archive in sorted(required, key=lambda item: item.filename):
        _obtain_archive(archive_root / archive.filename, archive, arguments.download)
    created = 0
    for case in CASES:
        destination = repository_root / case.name
        if destination.exists():
            _write_generated_files(case, destination)
            print(f"Already materialized: {destination.relative_to(ROOT)}")
            continue
        _materialize_case(case, archive_root, destination)
        created += 1
        print(f"Materialized: {destination.relative_to(ROOT)}")
    print(
        f"Historical snapshots ready: {len(CASES)} total, {created} newly created. "
        "No repository code was executed."
    )


def _obtain_archive(path: Path, archive: Archive, allow_download: bool) -> None:
    if not path.is_file():
        if not allow_download:
            raise SystemExit(
                f"Missing {path.relative_to(ROOT)}. Re-run with --download to fetch pinned archives."
            )
        temporary = path.with_suffix(".download")
        request = urllib.request.Request(
            archive.url,
            headers={"User-Agent": "TraceRepair-historical-benchmark/0.7"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response, temporary.open(
                "wb"
            ) as stream:
                shutil.copyfileobj(response, stream, length=1024 * 1024)
            temporary.replace(path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    actual = _file_sha256(path)
    if actual != archive.sha256:
        raise SystemExit(
            f"Archive checksum mismatch for {path.name}: expected {archive.sha256}, got {actual}"
        )
    print(f"Verified archive: {path.name} sha256={actual[:12]}")


def _materialize_case(case: HistoricalCase, archive_root: Path, destination: Path) -> None:
    build_root = ROOT / ".tmp" / f"benchmark-prepare-{uuid4().hex}"
    buggy_root = build_root / "buggy"
    fixed_root = build_root / "fixed"
    try:
        _safe_extract(archive_root / case.buggy.filename, buggy_root)
        _safe_extract(archive_root / case.fixed.filename, fixed_root)
        buggy_tree = _single_top_directory(buggy_root)
        fixed_tree = _single_top_directory(fixed_root)
        shutil.copytree(buggy_tree, destination)
        generated_paths = {relative for relative, _ in case.generated_files}
        if case.regression_test not in generated_paths:
            fixed_test = (fixed_tree / case.regression_test).resolve()
            if not fixed_test.is_file() or not fixed_test.is_relative_to(
                fixed_tree.resolve()
            ):
                raise SystemExit(
                    f"Pinned regression test is missing: {case.regression_test}"
                )
            target_test = destination / case.regression_test
            target_test.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fixed_test, target_test)
        _write_generated_files(case, destination)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(build_root, ignore_errors=True)


def _write_generated_files(case: HistoricalCase, repository: Path) -> None:
    """Create deterministic build artifacts required to import a source archive."""

    resolved_repository = repository.resolve()
    for relative, content in case.generated_files:
        target = (resolved_repository / PurePosixPath(relative)).resolve()
        if not target.is_relative_to(resolved_repository):
            raise SystemExit(f"Generated file escapes repository: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")


def _safe_extract(path: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            member = PurePosixPath(info.filename)
            mode = info.external_attr >> 16
            if (
                member.is_absolute()
                or ".." in member.parts
                or not member.parts
                or stat.S_ISLNK(mode)
            ):
                raise SystemExit(f"Unsafe archive member rejected in {path.name}")
            target = destination.joinpath(*member.parts).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise SystemExit(f"Archive member escapes destination in {path.name}")
        archive.extractall(destination)


def _single_top_directory(path: Path) -> Path:
    children = [child for child in path.iterdir() if child.is_dir()]
    if len(children) != 1 or any(child.is_file() for child in path.iterdir()):
        raise SystemExit("Pinned source archive must contain one top-level directory")
    return children[0]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
