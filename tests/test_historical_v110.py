import json
from pathlib import Path

from tracerepair.benchmark_suite import BenchmarkManifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evaluation" / "benchmarks" / "historical-python-v1.1.0.json"


def test_v110_has_three_development_and_two_unseen_locked_repositories() -> None:
    manifest = BenchmarkManifest.load(MANIFEST)

    assert manifest.agent_version == "0.6.0-dev1"
    assert len(manifest.tasks) == 5
    assert sum(task.split == "development" for task in manifest.tasks) == 3
    assert sum(task.split == "locked" for task in manifest.tasks) == 2
    assert len({task.source.repository_url for task in manifest.tasks}) == 5

    previous = json.loads(
        (ROOT / "evaluation" / "benchmarks" / "historical-python-v1.0.0.json").read_text(
            encoding="utf-8"
        )
    )
    previous_repositories = {
        task["source"]["repository_url"] for task in previous["tasks"]
    }
    locked_repositories = {
        task.source.repository_url for task in manifest.tasks if task.split == "locked"
    }
    assert locked_repositories.isdisjoint(previous_repositories)


def test_v110_task_sources_use_distinct_buggy_and_fixed_commits() -> None:
    manifest = BenchmarkManifest.load(MANIFEST)

    assert all(task.source.buggy_commit != task.source.fixed_commit for task in manifest.tasks)
    assert len({task.source.fixed_commit for task in manifest.tasks}) == 5
