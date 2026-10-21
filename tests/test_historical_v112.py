import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "evaluation" / "benchmarks" / "historical-python-v1.1.1.json"
NEW = ROOT / "evaluation" / "benchmarks" / "historical-python-v1.1.2.json"


def test_v112_changes_agent_version_without_changing_tasks_or_splits() -> None:
    old = json.loads(OLD.read_text(encoding="utf-8"))
    new = json.loads(NEW.read_text(encoding="utf-8"))

    assert old["benchmark_id"] == "historical-python-v1.1.1"
    assert old["agent_version"] == "0.6.0-dev2"
    assert new["benchmark_id"] == "historical-python-v1.1.2"
    assert new["agent_version"] == "0.6.0-dev3"
    assert new["tasks"] == old["tasks"]
    assert sum(task["split"] == "development" for task in new["tasks"]) == 3
    assert sum(task["split"] == "locked" for task in new["tasks"]) == 2
