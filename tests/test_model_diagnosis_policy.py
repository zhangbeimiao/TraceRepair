from tracerepair.read_tools import ReadOnlyResult, SearchHit
from scripts.model_diagnosis_loop import _next_allowed_tools


def test_empty_search_stays_in_discovery_stage() -> None:
    assert _next_allowed_tools("search_code", ReadOnlyResult(ok=True, data=[])) == {
        "repo_map",
        "search_code",
    }


def test_search_hit_unlocks_read_file_only() -> None:
    result = ReadOnlyResult(ok=True, data=[SearchHit("src/eventrelay/config.py", 5, "read_bool")])
    assert _next_allowed_tools("search_code", result) == {"search_code", "read_file"}


def test_failed_search_does_not_unlock_read_file() -> None:
    result = ReadOnlyResult.failure("INVALID_QUERY", "bad query")
    assert _next_allowed_tools("search_code", result) == {"repo_map", "search_code"}
