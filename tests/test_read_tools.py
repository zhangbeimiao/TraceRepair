from pathlib import Path

from tracerepair.read_tools import ReadOnlyRepository


REPO_ROOT = Path(__file__).parents[1]


def test_repo_map_includes_source_symbols_but_not_tests() -> None:
    repository = ReadOnlyRepository(REPO_ROOT)
    result = repository.repo_map()

    assert result.ok is True
    assert result.data is not None
    summaries = {item.path: item for item in result.data}
    assert "src/eventrelay/processor.py" in summaries
    assert "EventProcessor" in summaries["src/eventrelay/processor.py"].symbols
    assert not any(path.startswith("tests/") for path in summaries)


def test_search_returns_bounded_case_insensitive_hits() -> None:
    repository = ReadOnlyRepository(REPO_ROOT)
    result = repository.search_code("eventprocessor", max_hits=2)

    assert result.ok is True
    assert result.data is not None
    assert 1 <= len(result.data) <= 2
    assert all(hit.path.startswith("src/") for hit in result.data)


def test_read_file_returns_requested_line_slice() -> None:
    repository = ReadOnlyRepository(REPO_ROOT, max_read_lines=10)
    result = repository.read_file("src/eventrelay/config.py", start_line=1, end_line=3)

    assert result.ok is True
    assert result.data is not None
    assert result.data.start_line == 1
    assert "import os" in result.data.content


def test_path_traversal_and_test_reads_are_denied() -> None:
    repository = ReadOnlyRepository(REPO_ROOT)

    traversal = repository.read_file("../../Windows/System32/drivers/etc/hosts")
    tests = repository.read_file("tests/test_processor.py")
    agent_source = repository.read_file("src/tracerepair/model_planner.py")

    assert traversal.error is not None and traversal.error.code == "PATH_DENIED"
    assert tests.error is not None and tests.error.code == "PATH_DENIED"
    assert agent_source.error is not None and agent_source.error.code == "PATH_DENIED"


def test_read_limits_and_missing_files_are_structured_errors() -> None:
    repository = ReadOnlyRepository(REPO_ROOT, max_read_lines=3)

    too_many_lines = repository.read_file("src/eventrelay/config.py", start_line=1, end_line=4)
    missing = repository.read_file("src/eventrelay/missing.py")

    assert too_many_lines.error is not None and too_many_lines.error.code == "LINE_LIMIT_EXCEEDED"
    assert missing.error is not None and missing.error.code == "FILE_NOT_FOUND"
