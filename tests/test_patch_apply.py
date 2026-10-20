from pathlib import Path

from evaluation.materialize import materialize_case
from tracerepair.patch_apply import PatchApplier
from tracerepair.patch_policy import PatchPolicy
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


def _symbol_workspace(tmp_path: Path, body: str) -> tuple[Path, Path]:
    workspace = tmp_path / "repository"
    target = workspace / "src" / "sample" / "logic.py"
    target.parent.mkdir(parents=True)
    target.write_text(body, encoding="utf-8")
    return workspace, target


def test_unique_exact_context_can_relocate_beyond_window_inside_named_symbol(
    tmp_path: Path,
) -> None:
    padding = "".join(f"# padding {index}\n" for index in range(100))
    source = padding + """class Bucket:
    def __init__(self, iterable, key, validator=None):
        self._it = iter(iterable)
        self._key = key
        self._validator = validator or (lambda value: True)
        self._ready = True
"""
    workspace, target = _symbol_workspace(tmp_path, source)
    candidate = """--- a/src/sample/logic.py
+++ b/src/sample/logic.py
@@ -2,4 +2,4 @@
         self._it = iter(iterable)
         self._key = key
-        self._validator = validator or (lambda value: True)
+        self._validator = validator if validator is not None else (lambda value: True)
         self._ready = True
"""

    result = PatchApplier(
        workspace, PatchPolicy(allowed_roots=("src/sample",))
    ).apply(candidate)

    assert result.ok is True
    assert "validator if validator is not None" in target.read_text(encoding="utf-8")
    assert len(result.relocations) == 1
    relocation = result.relocations[0]
    assert relocation.mode == "symbol_exact"
    assert relocation.symbol == "function:__init__"
    assert relocation.advertised_line == 2
    assert relocation.applied_line > 80


def test_far_exact_top_level_context_is_rejected_without_writing(tmp_path: Path) -> None:
    padding = "".join(f"# padding {index}\n" for index in range(100))
    source = padding + "enabled = True\nanswer = 1\nmarker = 'end'\n"
    workspace, target = _symbol_workspace(tmp_path, source)
    before = target.read_text(encoding="utf-8")
    candidate = """--- a/src/sample/logic.py
+++ b/src/sample/logic.py
@@ -2,3 +2,3 @@
 enabled = True
-answer = 1
+answer = 2
 marker = 'end'
"""

    result = PatchApplier(
        workspace, PatchPolicy(allowed_roots=("src/sample",))
    ).apply(candidate)

    assert result.ok is False
    assert result.error_code == "PATCH_CONTEXT_MISMATCH"
    assert target.read_text(encoding="utf-8") == before


def test_far_symbol_relocation_requires_globally_unique_context(tmp_path: Path) -> None:
    padding = "".join(f"# padding {index}\n" for index in range(100))
    repeated = """    def update(self):
        before = self.value
        self.value = 1
        return before
"""
    source = padding + "class First:\n" + repeated + "\nclass Second:\n" + repeated
    workspace, target = _symbol_workspace(tmp_path, source)
    before = target.read_text(encoding="utf-8")
    candidate = """--- a/src/sample/logic.py
+++ b/src/sample/logic.py
@@ -2,3 +2,3 @@
         before = self.value
-        self.value = 1
+        self.value = 2
         return before
"""

    result = PatchApplier(
        workspace, PatchPolicy(allowed_roots=("src/sample",))
    ).apply(candidate)

    assert result.ok is False
    assert result.error_code == "PATCH_CONTEXT_AMBIGUOUS"
    assert target.read_text(encoding="utf-8") == before


def test_far_symbol_relocation_requires_context_and_a_removed_line(
    tmp_path: Path,
) -> None:
    padding = "".join(f"# padding {index}\n" for index in range(100))
    source = padding + """def configure(validator=None):
    key = "validator"
    selected = validator or (lambda value: True)
    return key, selected
"""
    candidates = (
        """--- a/src/sample/logic.py
+++ b/src/sample/logic.py
@@ -2,2 +2,2 @@
-    selected = validator or (lambda value: True)
+    selected = validator if validator is not None else (lambda value: True)
     return key, selected
""",
        """--- a/src/sample/logic.py
+++ b/src/sample/logic.py
@@ -2,2 +2,3 @@
     key = "validator"
+    explicitly_configured = validator is not None
     selected = validator or (lambda value: True)
""",
    )

    for index, candidate in enumerate(candidates):
        workspace, target = _symbol_workspace(tmp_path / str(index), source)
        before = target.read_text(encoding="utf-8")
        result = PatchApplier(
            workspace, PatchPolicy(allowed_roots=("src/sample",))
        ).apply(candidate)

        assert result.ok is False
        assert result.error_code == "PATCH_CONTEXT_MISMATCH"
        assert target.read_text(encoding="utf-8") == before
