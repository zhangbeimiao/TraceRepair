from dataclasses import replace
from pathlib import Path

import pytest

from scripts.prepare_historical_benchmark import HTTPIE_OFFLINE_ORACLE
from tracerepair.oracle_validation import (
    _HTTPIE_OFFLINE_ORACLE,
    OracleValidationError,
    validate_oracle_pair,
)
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


def test_oracle_error_includes_bounded_pytest_diagnostics(tmp_path: Path) -> None:
    buggy = _repository(tmp_path / "buggy", 1)
    fixed = _repository(tmp_path / "fixed", 2)
    (buggy / "tests" / "test_logic.py").write_text(
        "def test_value(:\n", encoding="utf-8"
    )
    spec = _spec(buggy)

    with pytest.raises(OracleValidationError, match="stdout=.*SyntaxError"):
        validate_oracle_pair(
            "sample-value", spec, buggy, replace(spec, repository_root=fixed), fixed
        )


def test_httpie_offline_oracle_is_identical_in_preparation_and_validation() -> None:
    assert HTTPIE_OFFLINE_ORACLE == _HTTPIE_OFFLINE_ORACLE
    assert "socket" not in HTTPIE_OFFLINE_ORACLE
    assert "httpbin.org" not in HTTPIE_OFFLINE_ORACLE
