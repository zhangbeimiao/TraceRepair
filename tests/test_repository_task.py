import json
from pathlib import Path

import pytest

from tracerepair.repository_task import (
    RepositoryTaskError,
    RepositoryTaskSpec,
    materialize_repository,
    runtime_spec,
)


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "examples" / "tasks" / "mini-repo.json"


def test_loads_relative_repository_and_validates_boundaries() -> None:
    spec = RepositoryTaskSpec.load(CONFIG)

    assert spec.name == "mini-repo-discount"
    assert spec.repository_root == (ROOT / "examples" / "mini_repo").resolve()
    assert spec.source_allowlist == ("src/minimath",)
    assert spec.target_test.endswith("::test_apply_discount_returns_remaining_price")


def test_materializes_bounded_disposable_copy(tmp_path: Path) -> None:
    spec = RepositoryTaskSpec.load(CONFIG)
    workspace = materialize_repository(spec, tmp_path / "workspace")

    assert (workspace / "src/minimath/pricing.py").is_file()
    assert (workspace / "tests/test_pricing.py").is_file()
    resumed = runtime_spec(spec.runtime_payload(), workspace, spec.issue)
    assert resumed.target_test == spec.target_test


def test_rejects_path_traversal_and_pytest_options() -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["repository_root"] = str((ROOT / "examples" / "mini_repo").resolve())
    payload["source_allowlist"] = ["../outside"]
    with pytest.raises(RepositoryTaskError, match="unsafe path"):
        RepositoryTaskSpec.from_mapping(payload)

    payload["source_allowlist"] = ["src/minimath"]
    payload["target_test"] = "tests/test_pricing.py -k discount"
    with pytest.raises(RepositoryTaskError, match="bounded pytest"):
        RepositoryTaskSpec.from_mapping(payload)


def test_rejects_repository_above_configured_file_limit(tmp_path: Path) -> None:
    repository = tmp_path / "small-repo"
    (repository / "src/pkg").mkdir(parents=True)
    (repository / "tests").mkdir()
    (repository / "src/pkg/a.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repository / "tests/test_a.py").write_text("def test_a(): assert True\n", encoding="utf-8")
    (repository / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    payload = {
        "name": "limited-repo",
        "repository_root": str(repository),
        "issue": "a bounded example issue",
        "source_allowlist": ["src/pkg"],
        "target_test": "tests/test_a.py::test_a",
        "regression_suite": "tests",
        "diagnostic_queries": ["VALUE"],
        "max_repository_files": 2,
    }

    with pytest.raises(RepositoryTaskError, match="max_repository_files"):
        RepositoryTaskSpec.from_mapping(payload)


def test_accepts_legacy_pytest_configuration_in_setup_cfg(tmp_path: Path) -> None:
    repository = tmp_path / "legacy-repo"
    (repository / "legacy").mkdir(parents=True)
    (repository / "tests").mkdir()
    (repository / "legacy" / "logic.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repository / "tests" / "test_logic.py").write_text(
        "def test_value(): assert True\n", encoding="utf-8"
    )
    (repository / "setup.cfg").write_text("[tool:pytest]\n", encoding="utf-8")

    spec = RepositoryTaskSpec.from_mapping(
        {
            "name": "legacy-repo",
            "repository_root": str(repository),
            "issue": "legacy repositories commonly configure pytest in setup.cfg",
            "source_allowlist": ["legacy"],
            "target_test": "tests/test_logic.py::test_value",
            "regression_suite": "tests/test_logic.py",
            "diagnostic_queries": ["VALUE"],
            "pythonpath": ["."],
        }
    )

    assert spec.repository_root == repository.resolve()
