"""Tests for `quoriv.repo.symbols` — multi-language definition + reference extraction."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from quoriv.repo.symbols import (
    CONTAINER_KINDS,
    DEFINITION_KINDS,
    Symbol,
    extract_definitions,
    find_references,
)

# ---------------------------------------------------------------------------
# Symbol dataclass
# ---------------------------------------------------------------------------


class TestSymbol:
    def test_is_frozen(self) -> None:
        s = Symbol(name="x", kind="function", lineno=1, col_offset=0)
        with pytest.raises(FrozenInstanceError):
            s.name = "y"  # type: ignore[misc]

    def test_default_parent_is_none(self) -> None:
        assert Symbol(name="x", kind="function", lineno=1, col_offset=0).parent is None


# ---------------------------------------------------------------------------
# Definition tables
# ---------------------------------------------------------------------------


class TestDefinitionTables:
    def test_known_languages(self) -> None:
        for lang in ("python", "javascript", "typescript", "go", "rust", "java"):
            assert lang in DEFINITION_KINDS, f"missing kind map for {lang}"

    def test_container_kinds_sane(self) -> None:
        assert "class" in CONTAINER_KINDS
        assert "struct" in CONTAINER_KINDS


# ---------------------------------------------------------------------------
# Python via tree-sitter
# ---------------------------------------------------------------------------


_PY_SRC = """\
def hello():
    return 1

async def fetch():
    return None

class Foo:
    def bar(self):
        return hello() + 1
"""


class TestPythonExtraction:
    def test_finds_top_level_function(self) -> None:
        defs = extract_definitions(_PY_SRC, "python")
        names = {d.name for d in defs}
        assert "hello" in names
        assert "fetch" in names

    def test_finds_class(self) -> None:
        defs = extract_definitions(_PY_SRC, "python")
        cls = next(d for d in defs if d.name == "Foo")
        assert cls.kind == "class"

    def test_method_records_parent(self) -> None:
        defs = extract_definitions(_PY_SRC, "python")
        bar = next(d for d in defs if d.name == "bar")
        assert bar.parent == "Foo"
        assert bar.kind == "function"

    def test_target_filter(self) -> None:
        defs = extract_definitions(_PY_SRC, "python", target="hello")
        assert [d.name for d in defs] == ["hello"]

    def test_references_include_definition_and_call(self) -> None:
        refs = find_references(_PY_SRC, "python", "hello")
        # def site at line 1, call site at line 9
        linenos = sorted(r.lineno for r in refs)
        assert 1 in linenos
        assert 9 in linenos

    def test_empty_target_returns_empty(self) -> None:
        assert find_references(_PY_SRC, "python", "") == []


# ---------------------------------------------------------------------------
# Go via tree-sitter
# ---------------------------------------------------------------------------


_GO_SRC = """\
package main

type Widget struct {
    Name string
}

func (w *Widget) Show() {
    println(w.Name)
}

func main() {
    w := Widget{Name: "hi"}
    w.Show()
}
"""


class TestGoExtraction:
    def test_finds_type_method_function(self) -> None:
        defs = extract_definitions(_GO_SRC, "go")
        names_kinds = {(d.name, d.kind) for d in defs}
        assert ("Widget", "type") in names_kinds
        assert ("Show", "method") in names_kinds
        assert ("main", "function") in names_kinds

    def test_references_widget(self) -> None:
        refs = find_references(_GO_SRC, "go", "Widget")
        # Should include: type declaration, method receiver, struct literal.
        assert len(refs) >= 3
        assert all(r.name == "Widget" for r in refs)


# ---------------------------------------------------------------------------
# TypeScript via tree-sitter
# ---------------------------------------------------------------------------


_TS_SRC = """\
interface Pet { name: string; }
type Age = number;
class Dog implements Pet {
    name = "rex";
    bark(): void { console.log(this.name); }
}
function pet(d: Dog): void { d.bark(); }
"""


class TestTypeScriptExtraction:
    def test_extracts_all_kinds(self) -> None:
        defs = extract_definitions(_TS_SRC, "typescript")
        kinds = {d.kind for d in defs}
        assert {"interface", "type", "class", "method", "function"} <= kinds

    def test_method_records_parent_class(self) -> None:
        defs = extract_definitions(_TS_SRC, "typescript")
        bark = next(d for d in defs if d.name == "bark")
        assert bark.parent == "Dog"


# ---------------------------------------------------------------------------
# Rust via tree-sitter
# ---------------------------------------------------------------------------


_RUST_SRC = """\
struct Widget {
    name: String,
}

trait Renderer {
    fn render(&self);
}

impl Renderer for Widget {
    fn render(&self) {
        println!("{}", self.name);
    }
}

fn main() {
    let w = Widget { name: String::from("hi") };
    w.render();
}
"""


class TestRustExtraction:
    def test_finds_struct_trait_impl_fn(self) -> None:
        defs = extract_definitions(_RUST_SRC, "rust")
        kinds = {d.kind for d in defs}
        assert {"struct", "trait", "impl", "function"} <= kinds


# ---------------------------------------------------------------------------
# Unsupported language graceful return
# ---------------------------------------------------------------------------


class TestUnsupportedLanguage:
    def test_returns_empty_list(self) -> None:
        # A language without a DEFINITION_KINDS entry should return [] —
        # no exception, no surprise.
        assert extract_definitions("anything", "klingon") == []
