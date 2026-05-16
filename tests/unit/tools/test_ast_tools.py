"""Tests for `quoriv.tools.ast_tools`."""

from __future__ import annotations

from pathlib import Path

from quoriv.tools import QUORIV_TOOLS
from quoriv.tools.ast_tools import find_references, find_symbol, go_to_definition


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


# ---------------------------------------------------------------------------
# Slice 4b — multi-language find_symbol via tree-sitter.
# ---------------------------------------------------------------------------


class TestFindSymbolMultiLanguage:
    def test_finds_go_function(self, tmp_path: Path) -> None:
        _write(tmp_path, "main.go", "package main\nfunc Hello() {}\n")
        results = find_symbol.invoke({"name": "Hello", "path": str(tmp_path)})
        assert len(results) == 1
        assert results[0]["kind"] == "function"
        assert results[0]["lineno"] == 2

    def test_finds_typescript_class_and_method(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "x.ts",
            "class Dog { bark(): void { console.log('w'); } }\n",
        )
        cls = find_symbol.invoke({"name": "Dog", "path": str(tmp_path)})
        assert cls and cls[0]["kind"] == "class"
        method = find_symbol.invoke({"name": "bark", "path": str(tmp_path)})
        assert method and method[0]["parent"] == "Dog"

    def test_finds_rust_struct(self, tmp_path: Path) -> None:
        _write(tmp_path, "lib.rs", "struct Widget { name: String }\n")
        results = find_symbol.invoke({"name": "Widget", "path": str(tmp_path)})
        assert results and results[0]["kind"] == "struct"

    def test_skips_node_modules_and_target(self, tmp_path: Path) -> None:
        _write(tmp_path, "node_modules/lib/a.js", "function hidden() {}\n")
        _write(tmp_path, "target/debug/x.rs", "fn hidden() {}\n")
        _write(tmp_path, "real.go", "package main\nfunc hidden() {}\n")
        results = find_symbol.invoke({"name": "hidden", "path": str(tmp_path)})
        # Only the file outside excluded dirs should match.
        assert len(results) == 1
        assert "real.go" in results[0]["file"]

    def test_mixed_python_and_other_languages(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py", "def shared() -> None:\n    pass\n")
        _write(tmp_path, "b.go", "package main\nfunc shared() {}\n")
        _write(tmp_path, "c.ts", "function shared() {}\n")
        results = find_symbol.invoke({"name": "shared", "path": str(tmp_path)})
        files = {Path(r["file"]).suffix for r in results}
        assert ".py" in files
        assert ".go" in files
        assert ".ts" in files


# ---------------------------------------------------------------------------
# Slice 4b — go_to_definition (alias semantics for find_symbol)
# ---------------------------------------------------------------------------


class TestGoToDefinition:
    def test_returns_same_shape_as_find_symbol(self, tmp_path: Path) -> None:
        _write(tmp_path, "main.go", "package main\nfunc Hello() {}\n")
        a = find_symbol.invoke({"name": "Hello", "path": str(tmp_path)})
        b = go_to_definition.invoke({"name": "Hello", "path": str(tmp_path)})
        assert a == b

    def test_nonexistent_path_returns_empty(self, tmp_path: Path) -> None:
        results = go_to_definition.invoke({"name": "x", "path": str(tmp_path / "does-not-exist")})
        assert results == []

    def test_is_registered(self) -> None:
        assert hasattr(go_to_definition, "name")
        assert go_to_definition.name == "go_to_definition"
        names = {t.name for t in QUORIV_TOOLS}
        assert "go_to_definition" in names


# ---------------------------------------------------------------------------
# Slice 4b — find_references
# ---------------------------------------------------------------------------


class TestFindReferences:
    def test_finds_callsite_and_definition_in_go(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "main.go",
            "package main\nfunc Hello() {}\nfunc main() { Hello() }\n",
        )
        refs = find_references.invoke({"name": "Hello", "path": str(tmp_path)})
        assert len(refs) >= 2
        assert all(r["name"] == "Hello" for r in refs)
        linenos = sorted({r["lineno"] for r in refs})
        # Definition on line 2, call on line 3.
        assert 2 in linenos
        assert 3 in linenos

    def test_typescript_field_access(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "x.ts",
            "class Dog { name = 'rex'; bark(): void { console.log(this.name); } }\n",
        )
        refs = find_references.invoke({"name": "name", "path": str(tmp_path)})
        # Property declaration + ``this.name`` usage.
        assert len(refs) >= 2

    def test_no_match_returns_empty(self, tmp_path: Path) -> None:
        _write(tmp_path, "main.go", "package main\nfunc Hello() {}\n")
        assert find_references.invoke({"name": "nope", "path": str(tmp_path)}) == []

    def test_empty_name_returns_empty(self, tmp_path: Path) -> None:
        _write(tmp_path, "main.go", "package main\n")
        assert find_references.invoke({"name": "", "path": str(tmp_path)}) == []

    def test_nonexistent_path_returns_empty(self, tmp_path: Path) -> None:
        results = find_references.invoke({"name": "x", "path": str(tmp_path / "does-not-exist")})
        assert results == []

    def test_is_registered(self) -> None:
        assert hasattr(find_references, "name")
        assert find_references.name == "find_references"
        names = {t.name for t in QUORIV_TOOLS}
        assert "find_references" in names
