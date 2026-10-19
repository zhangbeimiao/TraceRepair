import tomllib
from pathlib import Path

from tracerepair.version import PROJECT_VERSION


def test_project_version_matches_package_metadata() -> None:
    root = Path(__file__).parents[1]
    payload = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    assert payload["project"]["version"] == PROJECT_VERSION
