from pathlib import Path

from evaluation.materialize import materialize_case
from tracerepair.patch_apply import PatchApplier
from tracerepair.test_runner import RestrictedTestRunner


FIX_CASE_05 = """--- a/src/eventrelay/config.py
+++ b/src/eventrelay/config.py
@@ -6,6 +6,4 @@
     if value is None:
         return default
     normalized = value.strip().lower()
-    if value:
-        return True
     if normalized in {\"1\", \"true\", \"yes\", \"on\"}:
         return True
"""


def test_policy_approved_patch_repairs_disposable_case(tmp_path: Path) -> None:
    workspace = materialize_case("05", tmp_path / "case-05")
    result = PatchApplier(workspace).apply(FIX_CASE_05)

    assert result.ok is True
    assert result.files == ("src/eventrelay/config.py",)
    runner = RestrictedTestRunner(workspace)
    assert runner.run_tests("tests/test_repair_targets.py::test_case_05_parses_false_as_false").ok is True


def test_rejected_patch_does_not_write_workspace(tmp_path: Path) -> None:
    workspace = materialize_case("05", tmp_path / "case-05")
    target = workspace / "src/eventrelay/config.py"
    before = target.read_text(encoding="utf-8")
    unsafe = FIX_CASE_05.replace("src/eventrelay/config.py", "tests/test_config.py")

    result = PatchApplier(workspace).apply(unsafe)

    assert result.ok is False
    assert result.error_code == "PATCH_POLICY_DENIED"
    assert target.read_text(encoding="utf-8") == before


def test_mismatched_hunk_does_not_write_workspace(tmp_path: Path) -> None:
    workspace = materialize_case("05", tmp_path / "case-05")
    target = workspace / "src/eventrelay/config.py"
    before = target.read_text(encoding="utf-8")
    mismatch = FIX_CASE_05.replace("normalized = value.strip().lower()", "normalized = missing")

    result = PatchApplier(workspace).apply(mismatch)

    assert result.ok is False
    assert result.error_code == "PATCH_CONTEXT_MISMATCH"
    assert target.read_text(encoding="utf-8") == before


def test_unique_exact_context_allows_small_hunk_line_relocation(tmp_path: Path) -> None:
    workspace = materialize_case("05", tmp_path / "case-05")
    shifted = FIX_CASE_05.replace("@@ -6,6 +6,4 @@", "@@ -3,6 +3,4 @@")

    result = PatchApplier(workspace).apply(shifted)

    assert result.ok is True
    runner = RestrictedTestRunner(workspace)
    assert runner.run_tests("tests/test_repair_targets.py::test_case_05_parses_false_as_false").ok is True


def test_ambiguous_relocated_context_is_rejected_without_writing(tmp_path: Path) -> None:
    workspace = materialize_case("05", tmp_path / "case-05")
    target = workspace / "src/eventrelay/config.py"
    before = target.read_text(encoding="utf-8")
    ambiguous = """--- a/src/eventrelay/config.py
+++ b/src/eventrelay/config.py
@@ -1,1 +1,1 @@
-        return True
+        return bool(1)
"""

    result = PatchApplier(workspace).apply(ambiguous)

    assert result.ok is False
    assert result.error_code == "PATCH_CONTEXT_AMBIGUOUS"
    assert target.read_text(encoding="utf-8") == before
