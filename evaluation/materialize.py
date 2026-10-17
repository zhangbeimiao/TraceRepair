"""Create a disposable faulty workspace from one catalogued EventRelay case."""

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "evaluation" / "cases.json"


def load_case(case_id: str) -> dict[str, str]:
    cases = json.loads(CATALOG.read_text(encoding="utf-8"))
    for case in cases:
        if case["id"] == case_id:
            return case
    raise KeyError(f"unknown case: {case_id}")


def materialize_case(case_id: str, destination: Path) -> Path:
    """Copy the baseline source and apply exactly one checked transformation."""
    case = load_case(case_id)
    if case.get("status") == "reserved_for_baseline_increment":
        raise ValueError(f"case {case_id} is not materialisable yet")
    if destination.exists():
        raise FileExistsError(destination)
    materialize_baseline(destination)
    (destination / "pytest.ini").write_text(
        "[pytest]\npythonpath = src\ntestpaths = tests\n",
        encoding="utf-8",
    )

    target = destination / case["file"]
    content = target.read_text(encoding="utf-8")
    occurrences = content.count(case["find"])
    if occurrences != 1:
        raise ValueError(f"case {case_id} expected one replacement, found {occurrences}")
    target.write_text(content.replace(case["find"], case["replace"], 1), encoding="utf-8")
    return destination


def materialize_baseline(destination: Path) -> Path:
    """Create an isolated, passing EventRelay workspace for a regression run."""
    if destination.exists():
        raise FileExistsError(destination)
    shutil.copytree(ROOT / "src", destination / "src")
    shutil.copytree(ROOT / "eventrelay_tests", destination / "tests")
    (destination / "pytest.ini").write_text(
        "[pytest]\npythonpath = src\ntestpaths = tests\n",
        encoding="utf-8",
    )
    return destination
