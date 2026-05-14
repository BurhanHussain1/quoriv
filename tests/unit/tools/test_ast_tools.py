"""Tests for `quoriv.tools.ast_tools`."""

from __future__ import annotations

from pathlib import Path

from quoriv.tools.ast_tools import find_symbol


def _write(tmp_path: Path, rel: str, content: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


class TestFindSymbol:
    def test_finds_function(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py", "def hello() -> None:\n    pass\n")
        results = find_symbol.invoke({"name": "hello", "path": str(tmp_path)})
        assert len(results) == 1
        assert results[0]["kind"] == "function"
        assert results[0]["name"] == "hello"
        assert results[0]["lineno"] == 1

    def test_finds_async_function(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py", "async def fetch() -> None:\n    pass\n")
        results = find_symbol.invoke({"name": "fetch", "path": str(tmp_path)})
        assert results[0]["kind"] == "async_function"

    def test_finds_class(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py", "class Widget:\n    pass\n")
        results = find_symbol.invoke({"name": "Widget", "path": str(tmp_path)})
        assert results[0]["kind"] == "class"

    def test_finds_method_with_parent(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "a.py",
            "class Widget:\n    def show(self) -> None:\n        pass\n",
        )
        results = find_symbol.invoke({"name": "show", "path": str(tmp_path)})
        assert len(results) == 1
        assert results[0]["kind"] == "function"
        assert results[0]["parent"] == "Widget"

    def test_finds_module_level_variable(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py", "ANSWER = 42\n")
        results = find_symbol.invoke({"name": "ANSWER", "path": str(tmp_path)})
        assert results[0]["kind"] == "variable"

    def test_no_match_returns_empty_list(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py", "def foo() -> None:\n    pass\n")
        assert find_symbol.invoke({"name": "bar", "path": str(tmp_path)}) == []

    def test_searches_subdirectories(self, tmp_path: Path) -> None:
        _write(tmp_path, "pkg/sub/a.py", "def needle() -> None:\n    pass\n")
        results = find_symbol.invoke({"name": "needle", "path": str(tmp_path)})
        assert len(results) == 1
        assert "sub" in results[0]["file"]

    def test_skips_venv_and_pycache(self, tmp_path: Path) -> None:
        _write(tmp_path, ".venv/lib/a.py", "def hidden() -> None:\n    pass\n")
        _write(tmp_path, "__pycache__/b.py", "def hidden() -> None:\n    pass\n")
        _write(tmp_path, "real.py", "def hidden() -> None:\n    pass\n")
        results = find_symbol.invoke({"name": "hidden", "path": str(tmp_path)})
        # Only the file outside excluded dirs should match.
        assert len(results) == 1
        assert "real.py" in results[0]["file"]

    def test_skips_syntactically_broken_file(self, tmp_path: Path) -> None:
        _write(tmp_path, "broken.py", "def oops(:\n")
        _write(tmp_path, "good.py", "def works() -> None:\n    pass\n")
        # Broken file is silently skipped; good file still matches.
        results = find_symbol.invoke({"name": "works", "path": str(tmp_path)})
        assert len(results) == 1

    def test_nonexistent_path_returns_empty(self, tmp_path: Path) -> None:
        results = find_symbol.invoke({"name": "anything", "path": str(tmp_path / "does-not-exist")})
        assert results == []

    def test_accepts_single_file_path(self, tmp_path: Path) -> None:
        f = _write(tmp_path, "one.py", "def lone() -> None:\n    pass\n")
        results = find_symbol.invoke({"name": "lone", "path": str(f)})
        assert len(results) == 1

    def test_is_registered_as_langchain_tool(self) -> None:
        # find_symbol is a BaseTool, not a bare function
        assert hasattr(find_symbol, "invoke")
        assert hasattr(find_symbol, "name")
        assert find_symbol.name == "find_symbol"
