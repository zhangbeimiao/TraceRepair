from tracerepair.patch_policy import PatchPolicy


SAFE_DIFF = """diff --git a/src/eventrelay/config.py b/src/eventrelay/config.py
--- a/src/eventrelay/config.py
+++ b/src/eventrelay/config.py
@@ -5,6 +5,7 @@ def read_bool(name: str, default: bool = False) -> bool:
     if value is None:
         return default
     normalized = value.strip().lower()
+    # Explicit values avoid Python string truthiness.
     if normalized in {\"1\", \"true\", \"yes\", \"on\"}:
         return True
"""


def test_policy_accepts_small_source_only_modification() -> None:
    result = PatchPolicy().validate(SAFE_DIFF)

    assert result.accepted is True
    assert result.files == ("src/eventrelay/config.py",)
    assert result.added_lines == 1


def test_policy_rejects_test_and_traversal_paths() -> None:
    tests_diff = SAFE_DIFF.replace("src/eventrelay/config.py", "tests/test_config.py")
    traversal_diff = SAFE_DIFF.replace("src/eventrelay/config.py", "src/eventrelay/../secrets.py")

    assert "PATH_DENIED" in PatchPolicy().validate(tests_diff).errors
    assert "PATH_DENIED" in PatchPolicy().validate(traversal_diff).errors


def test_policy_rejects_excessive_change_volume() -> None:
    additions = "\n".join(f"+line {index}" for index in range(4))
    diff = SAFE_DIFF + additions

    result = PatchPolicy(max_changed_lines=3).validate(diff)

    assert result.accepted is False
    assert "TOO_MANY_CHANGED_LINES" in result.errors


def test_policy_requires_hunk_and_target_file() -> None:
    result = PatchPolicy().validate("not a unified diff")

    assert result.accepted is False
    assert set(result.errors) == {"NO_TARGET_FILE", "NO_HUNK"}
