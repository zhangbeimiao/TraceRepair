"""Materialize pinned historical bug snapshots without executing repository code."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import stat
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]


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
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--download",
        action="store_true",
        help="download missing pinned archives; without this flag only cached archives are used",
    )
    arguments = parser.parse_args()
    if ROOT.drive.casefold() != "d:":
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
        fixed_test = (fixed_tree / case.regression_test).resolve()
        if not fixed_test.is_file() or not fixed_test.is_relative_to(fixed_tree.resolve()):
            raise SystemExit(f"Pinned regression test is missing: {case.regression_test}")
        shutil.copytree(buggy_tree, destination)
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
