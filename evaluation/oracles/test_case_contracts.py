import json
from pathlib import Path


def test_case_catalog_has_balanced_split() -> None:
    path = Path(__file__).parents[1] / "cases.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    assert len(cases) == 10
    assert [item["split"] for item in cases].count("development") == 5
    assert [item["split"] for item in cases].count("locked") == 5


def test_case_ids_and_sources_are_unique() -> None:
    path = Path(__file__).parents[1] / "cases.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    assert len({item["id"] for item in cases}) == len(cases)
    assert all(item["issue"] and item["file"] for item in cases)
