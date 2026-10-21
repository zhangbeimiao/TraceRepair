import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evaluation" / "benchmarks" / "historical-python-v1.1.0.json"


def test_v110_has_three_development_and_two_unseen_locked_repositories() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert manifest["agent_version"] == "0.6.0-dev1"
    assert len(manifest["tasks"]) == 5
    assert sum(task["split"] == "development" for task in manifest["tasks"]) == 3
    assert sum(task["split"] == "locked" for task in manifest["tasks"]) == 2
    assert len({task["source"]["repository_url"] for task in manifest["tasks"]}) == 5
    for task in manifest["tasks"]:
        config = (MANIFEST.parent / task["task_config"]).resolve()
        assert config.is_file()

    previous = json.loads(
        (ROOT / "evaluation" / "benchmarks" / "historical-python-v1.0.0.json").read_text(
            encoding="utf-8"
        )
    )
    previous_repositories = {
        task["source"]["repository_url"] for task in previous["tasks"]
    }
    locked_repositories = {
        task["source"]["repository_url"]
        for task in manifest["tasks"]
        if task["split"] == "locked"
    }
    assert locked_repositories.isdisjoint(previous_repositories)


def test_v110_task_sources_use_distinct_buggy_and_fixed_commits() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources = [task["source"] for task in manifest["tasks"]]

    assert all(source["buggy_commit"] != source["fixed_commit"] for source in sources)
    assert len({source["fixed_commit"] for source in sources}) == 5


def test_v110_compatibility_harnesses_are_outside_model_write_allowlists() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    for task in manifest["tasks"]:
        config_path = (MANIFEST.parent / task["task_config"]).resolve()
        config = json.loads(config_path.read_text(encoding="utf-8"))
        assert "conftest.py" not in config["source_allowlist"]
        assert "tests" not in config["source_allowlist"]
