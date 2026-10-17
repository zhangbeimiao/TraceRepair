"""Static safety checks for future candidate unified diffs."""

from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class PatchValidation:
    accepted: bool
    files: tuple[str, ...]
    added_lines: int
    removed_lines: int
    errors: tuple[str, ...]


class PatchPolicy:
    """Accept small modifications to EventRelay source only; never apply them."""

    def __init__(self, *, max_files: int = 3, max_changed_lines: int = 200, max_bytes: int = 30_000) -> None:
        self._max_files = max_files
        self._max_changed_lines = max_changed_lines
        self._max_bytes = max_bytes

    def validate(self, unified_diff: str) -> PatchValidation:
        errors: list[str] = []
        if not unified_diff.strip():
            errors.append("EMPTY_DIFF")
        if len(unified_diff.encode("utf-8")) > self._max_bytes:
            errors.append("DIFF_TOO_LARGE")

        files: list[str] = []
        added = 0
        removed = 0
        has_hunk = False
        for line in unified_diff.splitlines():
            if line.startswith("+++ "):
                raw_path = line[4:].removeprefix("b/")
                if raw_path == "/dev/null":
                    errors.append("FILE_DELETION_DENIED")
                    continue
                if not self._is_allowed_path(raw_path):
                    errors.append("PATH_DENIED")
                    continue
                files.append(raw_path)
            elif line.startswith("@@"):
                has_hunk = True
            elif line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed += 1

        unique_files = tuple(dict.fromkeys(files))
        if not files:
            errors.append("NO_TARGET_FILE")
        if not has_hunk:
            errors.append("NO_HUNK")
        if len(unique_files) > self._max_files:
            errors.append("TOO_MANY_FILES")
        if added + removed > self._max_changed_lines:
            errors.append("TOO_MANY_CHANGED_LINES")

        return PatchValidation(
            accepted=not errors,
            files=unique_files,
            added_lines=added,
            removed_lines=removed,
            errors=tuple(dict.fromkeys(errors)),
        )

    @staticmethod
    def _is_allowed_path(raw_path: str) -> bool:
        path = PurePosixPath(raw_path)
        return (
            not path.is_absolute()
            and ".." not in path.parts
            and len(path.parts) >= 3
            and path.parts[0:2] == ("src", "eventrelay")
            and path.suffix == ".py"
        )
