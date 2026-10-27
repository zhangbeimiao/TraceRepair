import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "compare_planner_protocols.py"


def _module():
    spec = importlib.util.spec_from_file_location("compare_planner_protocols", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_protocol_comparison_separates_format_and_test_failures() -> None:
    module = _module()

    assert module._is_format_failure("planner stopped safely: model reason is invalid")
    assert module._is_format_failure("model returned no native function call")
    assert not module._is_format_failure("candidate patch failed target test: TEST_FAILED")
    assert not module._is_format_failure("candidate patch rejected: PATCH_CONTEXT_MISMATCH")
