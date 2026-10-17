from pathlib import Path

import pytest

from evaluation.materialize import load_case, materialize_case


def test_known_case_can_be_materialised(tmp_path: Path) -> None:
    workspace = materialize_case("01", tmp_path / "case-01")
    code = (workspace / "src/eventrelay/idempotency.py").read_text(encoding="utf-8")
    assert "sorted(event.payload.items())" in code
    assert (workspace / "tests/test_repair_targets.py").is_file()
    assert (workspace / "pytest.ini").read_text(encoding="utf-8").startswith("[pytest]")


def test_unknown_case_is_rejected() -> None:
    with pytest.raises(KeyError):
        load_case("99")


def test_retention_case_can_be_materialised(tmp_path: Path) -> None:
    workspace = materialize_case("09", tmp_path / "case-09")
    code = (workspace / "src/eventrelay/retention.py").read_text(encoding="utf-8")
    assert "cutoff_seconds" in code


def test_every_catalogued_case_can_be_materialised(tmp_path: Path) -> None:
    for case_id in [f"{index:02d}" for index in range(1, 11)]:
        workspace = materialize_case(case_id, tmp_path / f"case-{case_id}")
        assert (workspace / "src/eventrelay").is_dir()
