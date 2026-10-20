from dataclasses import replace
from pathlib import Path

import pytest

from tracerepair.oracle_validation import OracleValidationError, validate_oracle_pair
from tracerepair.repository_task import RepositoryTaskSpec


def _repository(root: Path, value: int) -> Path:
    (root / "src" / "sample").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\npythonpath = ['src']\n", encoding="utf-8"
    )
    (root / "src" / "sample" / "logic.py").write_text(
        f"def value():\n    return {value}\n", encoding="utf-8"
    )
    (root / "tests" / "test_logic.py").write_text(
        "from sample.logic import value\n\ndef test_value():\n    assert value() == 2\n",
        encoding="utf-8",
    )
    return root


def _spec(root: Path) -> RepositoryTaskSpec:
    return RepositoryTaskSpec.from_mapping(
        {
            "name": "sample-value",
            "repository_root": str(root),
            "issue": "value returns one instead of two",
            "source_allowlist": ["src/sample"],
            "target_test": "tests/test_logic.py::test_value",
            "regression_suite": "tests",
            "diagnostic_queries": ["def value"],
            "pythonpath": ["src"],
        }
    )


def test_oracle_requires_buggy_failure_and_fixed_regression_pass(tmp_path: Path) -> None:
    buggy = _repository(tmp_path / "buggy", 1)
    fixed = _repository(tmp_path / "fixed", 2)
    spec = _spec(buggy)

    result = validate_oracle_pair(
        "sample-value", spec, buggy, replace(spec, repository_root=fixed), fixed
    )

    assert result.buggy_exit_code == 1
    assert result.fixed_target_passed is True
    assert result.fixed_regression_passed is True


def test_oracle_rejects_collection_error_as_invalid_bug_signal(tmp_path: Path) -> None:
    buggy = _repository(tmp_path / "buggy", 1)
    fixed = _repository(tmp_path / "fixed", 2)
    (buggy / "tests" / "test_logic.py").write_text(
        "import missing_dependency\n", encoding="utf-8"
    )
    spec = _spec(buggy)

    with pytest.raises(OracleValidationError, match="exit code 1"):
        validate_oracle_pair(
            "sample-value", spec, buggy, replace(spec, repository_root=fixed), fixed
        )
