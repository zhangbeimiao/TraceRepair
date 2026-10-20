"""Apply policy-approved unified diffs to disposable workspaces only."""

import ast
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from tracerepair.patch_policy import PatchPolicy, PatchValidation

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_MAX_HUNK_RELOCATION_LINES = 80
_MIN_SYMBOL_CONTEXT_LINES = 2


@dataclass(frozen=True)
class PatchApplyResult:
    ok: bool
    error_code: str | None
    files: tuple[str, ...]
    file_sha256: dict[str, str]
    validation: PatchValidation
    relocations: tuple["PatchRelocation", ...] = ()


@dataclass(frozen=True)
class PatchRelocation:
    path: str
    advertised_line: int
    applied_line: int
    mode: str
    symbol: str | None


@dataclass(frozen=True)
class _Hunk:
    old_start: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class _FilePatch:
    path: str
    hunks: tuple[_Hunk, ...]


class PatchApplier:
    """Validate all changes before writing, leaving tests and config untouched."""

    def __init__(self, workspace: Path, policy: PatchPolicy | None = None) -> None:
        resolved = workspace.resolve()
        if not resolved.is_dir():
            raise ValueError(f"workspace does not exist: {workspace}")
        self._workspace = resolved
        self._policy = policy or PatchPolicy()

    def apply(self, unified_diff: str) -> PatchApplyResult:
        validation = self._policy.validate(unified_diff)
        if not validation.accepted:
            return PatchApplyResult(False, "PATCH_POLICY_DENIED", (), {}, validation)
        try:
            patches = self._parse(unified_diff)
            replacements, relocations = self._build_replacements(patches)
        except ValueError as error:
            return PatchApplyResult(False, str(error), (), {}, validation)

        hashes: dict[str, str] = {}
        try:
            for path, content in replacements.items():
                target = self._safe_target(path)
                target.write_text(content, encoding="utf-8")
                hashes[path] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        except OSError:
            return PatchApplyResult(False, "PATCH_WRITE_FAILED", (), {}, validation)
        return PatchApplyResult(
            True,
            None,
            tuple(replacements),
            hashes,
            validation,
            relocations,
        )

    def _build_replacements(
        self, patches: tuple[_FilePatch, ...]
    ) -> tuple[dict[str, str], tuple[PatchRelocation, ...]]:
        replacements: dict[str, str] = {}
        relocations: list[PatchRelocation] = []
        for patch in patches:
            target = self._safe_target(patch.path)
            original = target.read_text(encoding="utf-8")
            content, patch_relocations = self._apply_hunks(
                original, patch.hunks, patch.path
            )
            replacements[patch.path] = content
            relocations.extend(patch_relocations)
        return replacements, tuple(relocations)

    def _safe_target(self, relative_path: str) -> Path:
        target = (self._workspace / relative_path).resolve()
        if not target.is_relative_to(self._workspace) or not target.is_file():
            raise ValueError("PATCH_FILE_NOT_FOUND")
        return target

    @staticmethod
    def _apply_hunks(
        original: str, hunks: tuple[_Hunk, ...], path: str
    ) -> tuple[str, tuple[PatchRelocation, ...]]:
        source = original.splitlines()
        output: list[str] = []
        relocations: list[PatchRelocation] = []
        source_index = 0
        for hunk in hunks:
            target_index, mode, symbol = PatchApplier._locate_hunk(
                source, hunk, source_index
            )
            relocations.append(
                PatchRelocation(
                    path=path,
                    advertised_line=hunk.old_start,
                    applied_line=target_index + 1,
                    mode=mode,
                    symbol=symbol,
                )
            )
            output.extend(source[source_index:target_index])
            source_index = target_index
            for line in hunk.lines:
                if line.startswith(" "):
                    if source_index >= len(source) or source[source_index] != line[1:]:
                        raise ValueError("PATCH_CONTEXT_MISMATCH")
                    output.append(line[1:])
                    source_index += 1
                elif line.startswith("-"):
                    if source_index >= len(source) or source[source_index] != line[1:]:
                        raise ValueError("PATCH_CONTEXT_MISMATCH")
                    source_index += 1
                elif line.startswith("+"):
                    output.append(line[1:])
                elif line != "\\ No newline at end of file":
                    raise ValueError("PATCH_PARSE_ERROR")
        output.extend(source[source_index:])
        suffix = "\n" if original.endswith("\n") else ""
        return "\n".join(output) + suffix, tuple(relocations)

    @staticmethod
    def _locate_hunk(
        source: list[str], hunk: _Hunk, minimum: int
    ) -> tuple[int, str, str | None]:
        """Locate one exact old block without allowing fuzzy application.

        Model-generated diffs occasionally have slightly inaccurate hunk line
        numbers.  Relocation never weakens content validation: every context and
        removed line must still match verbatim.  Nearby relocation remains bounded
        to 80 lines.  A farther relocation is accepted only when the exact block is
        globally unique and fully contained by one named Python function or class.
        """

        old_lines: list[str] = []
        for line in hunk.lines:
            if line.startswith((" ", "-")):
                old_lines.append(line[1:])
            elif line.startswith("+") or line == "\\ No newline at end of file":
                continue
            else:
                raise ValueError("PATCH_PARSE_ERROR")

        expected = hunk.old_start - 1
        if not old_lines:
            if minimum <= expected <= len(source):
                return expected, "advertised", None
            raise ValueError("PATCH_CONTEXT_MISMATCH")

        width = len(old_lines)
        if minimum <= expected and source[expected : expected + width] == old_lines:
            return expected, "advertised", None

        first = max(minimum, expected - _MAX_HUNK_RELOCATION_LINES, 0)
        last = min(len(source) - width, expected + _MAX_HUNK_RELOCATION_LINES)
        matches = [
            index
            for index in range(first, last + 1)
            if source[index : index + width] == old_lines
        ]
        if len(matches) == 1:
            return matches[0], "bounded_exact", None
        if len(matches) > 1:
            raise ValueError("PATCH_CONTEXT_AMBIGUOUS")

        global_matches = [
            index
            for index in range(max(minimum, 0), len(source) - width + 1)
            if source[index : index + width] == old_lines
        ]
        if len(global_matches) > 1:
            raise ValueError("PATCH_CONTEXT_AMBIGUOUS")
        if len(global_matches) == 1:
            removed_lines = sum(line.startswith("-") for line in hunk.lines)
            context_lines = sum(line.startswith(" ") for line in hunk.lines)
            target_index = global_matches[0]
            symbol = PatchApplier._named_symbol_for_range(
                source, target_index, width
            )
            if (
                removed_lines >= 1
                and context_lines >= _MIN_SYMBOL_CONTEXT_LINES
                and symbol is not None
            ):
                return target_index, "symbol_exact", symbol
        raise ValueError("PATCH_CONTEXT_MISMATCH")

    @staticmethod
    def _named_symbol_for_range(
        source: list[str], start_index: int, width: int
    ) -> str | None:
        """Return the smallest named AST scope containing an exact source block."""

        try:
            tree = ast.parse("\n".join(source) + "\n")
        except SyntaxError:
            return None
        start_line = start_index + 1
        end_line = start_index + width
        candidates = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.lineno <= start_line
            and getattr(node, "end_lineno", node.lineno) >= end_line
        ]
        if not candidates:
            return None
        node = min(
            candidates,
            key=lambda item: getattr(item, "end_lineno", item.lineno) - item.lineno,
        )
        kind = "class" if isinstance(node, ast.ClassDef) else "function"
        return f"{kind}:{node.name}"

    @staticmethod
    def _parse(unified_diff: str) -> tuple[_FilePatch, ...]:
        lines = unified_diff.splitlines()
        index = 0
        patches: list[_FilePatch] = []
        while index < len(lines):
            if lines[index].startswith("diff --git "):
                index += 1
                continue
            if not lines[index].startswith("--- a/"):
                index += 1
                continue
            source_path = lines[index][6:]
            index += 1
            if index >= len(lines) or not lines[index].startswith("+++ b/"):
                raise ValueError("PATCH_PARSE_ERROR")
            destination_path = lines[index][6:]
            if source_path != destination_path:
                raise ValueError("PATCH_RENAME_DENIED")
            index += 1
            hunks: list[_Hunk] = []
            while index < len(lines) and not lines[index].startswith("--- a/") and not lines[index].startswith("diff --git "):
                match = _HUNK_HEADER.match(lines[index])
                if match is None:
                    raise ValueError("PATCH_PARSE_ERROR")
                old_start = int(match.group(1))
                index += 1
                hunk_lines: list[str] = []
                while index < len(lines) and not lines[index].startswith("@@") and not lines[index].startswith("--- a/") and not lines[index].startswith("diff --git "):
                    hunk_lines.append(lines[index])
                    index += 1
                hunks.append(_Hunk(old_start, tuple(hunk_lines)))
            if not hunks:
                raise ValueError("PATCH_PARSE_ERROR")
            patches.append(_FilePatch(destination_path, tuple(hunks)))
        if not patches:
            raise ValueError("PATCH_PARSE_ERROR")
        return tuple(patches)
