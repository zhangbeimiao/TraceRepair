"""Bounded, read-only repository tools for a disposable case workspace."""

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, TypeVar


T = TypeVar("T")
_TEXT_SUFFIXES = {".md", ".py", ".json", ".toml", ".txt"}


@dataclass(frozen=True)
class ToolError:
    code: str
    message: str


@dataclass(frozen=True)
class ReadOnlyResult(Generic[T]):
    ok: bool
    data: T | None = None
    error: ToolError | None = None

    @classmethod
    def failure(cls, code: str, message: str) -> "ReadOnlyResult[Any]":
        return cls(ok=False, error=ToolError(code, message))


@dataclass(frozen=True)
class FileSummary:
    path: str
    line_count: int
    symbols: tuple[str, ...]


@dataclass(frozen=True)
class SearchHit:
    path: str
    line: int
    text: str


@dataclass(frozen=True)
class FileSlice:
    path: str
    start_line: int
    end_line: int
    content: str


class ReadOnlyRepository:
    """Expose a deliberately small, text-only view of a case workspace.

    The repository root is trusted configuration. All tool parameters are
    untrusted and are checked before opening any file.
    """

    def __init__(self, root: Path, *, max_read_lines: int = 200, max_search_hits: int = 30) -> None:
        resolved = root.resolve()
        if not resolved.is_dir():
            raise ValueError(f"repository root does not exist: {root}")
        self._root = resolved
        self._max_read_lines = max_read_lines
        self._max_search_hits = max_search_hits

    def repo_map(self, max_files: int = 100) -> ReadOnlyResult[list[FileSummary]]:
        if not 1 <= max_files <= 500:
            return ReadOnlyResult.failure("INVALID_LIMIT", "max_files must be between 1 and 500")
        summaries: list[FileSummary] = []
        for path in sorted(self._root.rglob("*")):
            if not path.is_file() or path.suffix not in _TEXT_SUFFIXES:
                continue
            relative = path.relative_to(self._root)
            if not self._is_allowed_relative(relative):
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            symbols = self._python_symbols(content) if path.suffix == ".py" else ()
            summaries.append(FileSummary(relative.as_posix(), len(content.splitlines()), symbols))
            if len(summaries) >= max_files:
                break
        return ReadOnlyResult(ok=True, data=summaries)

    def search_code(self, query: str, max_hits: int | None = None) -> ReadOnlyResult[list[SearchHit]]:
        if not 2 <= len(query) <= 200:
            return ReadOnlyResult.failure("INVALID_QUERY", "query length must be between 2 and 200")
        limit = max_hits if max_hits is not None else self._max_search_hits
        if not 1 <= limit <= self._max_search_hits:
            return ReadOnlyResult.failure(
                "INVALID_LIMIT", f"max_hits must be between 1 and {self._max_search_hits}"
            )
        hits: list[SearchHit] = []
        needle = query.casefold()
        for path in sorted(self._root.rglob("*")):
            if not path.is_file() or path.suffix not in _TEXT_SUFFIXES:
                continue
            relative = path.relative_to(self._root)
            if not self._is_allowed_relative(relative):
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for line_number, line in enumerate(lines, start=1):
                if needle in line.casefold():
                    hits.append(SearchHit(relative.as_posix(), line_number, line.strip()))
                    if len(hits) >= limit:
                        return ReadOnlyResult(ok=True, data=hits)
        return ReadOnlyResult(ok=True, data=hits)

    def read_file(
        self, path: str, start_line: int = 1, end_line: int | None = None
    ) -> ReadOnlyResult[FileSlice]:
        target = self._resolve_allowed_path(path)
        if isinstance(target, ToolError):
            return ReadOnlyResult(ok=False, error=target)
        if start_line < 1:
            return ReadOnlyResult.failure("INVALID_LINE_RANGE", "start_line must be at least 1")

        try:
            lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
        except UnicodeDecodeError:
            return ReadOnlyResult.failure("UNSUPPORTED_FILE", "file is not UTF-8 text")
        final_line = len(lines) if end_line is None else end_line
        if final_line < start_line:
            return ReadOnlyResult.failure("INVALID_LINE_RANGE", "end_line must not precede start_line")
        if final_line - start_line + 1 > self._max_read_lines:
            return ReadOnlyResult.failure(
                "LINE_LIMIT_EXCEEDED", f"at most {self._max_read_lines} lines may be read at once"
            )
        if start_line > len(lines):
            return ReadOnlyResult.failure("LINE_OUT_OF_RANGE", "start_line is beyond end of file")
        final_line = min(final_line, len(lines))
        relative = target.relative_to(self._root).as_posix()
        return ReadOnlyResult(
            ok=True,
            data=FileSlice(relative, start_line, final_line, "".join(lines[start_line - 1 : final_line])),
        )

    def _resolve_allowed_path(self, user_path: str) -> Path | ToolError:
        candidate = Path(user_path)
        if candidate.is_absolute():
            return ToolError("PATH_DENIED", "absolute paths are not allowed")
        target = (self._root / candidate).resolve()
        try:
            relative = target.relative_to(self._root)
        except ValueError:
            return ToolError("PATH_DENIED", "path escapes repository root")
        if not self._is_allowed_relative(relative):
            return ToolError("PATH_DENIED", "path is outside the read-only allowlist")
        if not target.is_file():
            return ToolError("FILE_NOT_FOUND", "requested file does not exist")
        if target.suffix not in _TEXT_SUFFIXES:
            return ToolError("UNSUPPORTED_FILE", "only approved text file types may be read")
        return target

    def _is_allowed_relative(self, path: Path) -> bool:
        return bool(path.parts) and (
            path.parts[0] == "docs" or path.parts[:2] == ("src", "eventrelay")
        )

    @staticmethod
    def _python_symbols(content: str) -> tuple[str, ...]:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return ("<syntax-error>",)
        return tuple(
            node.name
            for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        )
