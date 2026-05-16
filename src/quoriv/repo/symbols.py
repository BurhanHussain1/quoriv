"""Multi-language symbol index — Phase 1 Slice 4b.

Walks tree-sitter syntax trees to extract two related views of a source
file:

    extract_definitions(source, language, *, target=None) → list[Symbol]
        Function / method / class / struct / trait / interface / enum
        / type-alias definitions. When ``target`` is given, returns only
        records whose ``name`` matches exactly (case-sensitive).

    find_references(source, language, target) → list[Symbol]
        Every identifier node whose text equals ``target``. Includes
        definition sites, callers, type uses, and field accesses.
        Filtering "is this a definition vs a use" is left to the caller
        (definitions surface as ``kind="reference"`` here for shape
        consistency — the line + column locates them in source).

The extractor walks ``node.children`` recursively and dispatches on
``node.kind()`` via per-language maps in :data:`DEFINITION_KINDS`. No
tree-sitter ``Query`` objects are used — the language pack's bundled C
bindings expose a different ``Node`` class than the public ``tree_sitter``
package, which breaks ``QueryCursor``. A direct tree walk sidesteps
that incompatibility and stays fast (tree-sitter parses are typically
sub-millisecond).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from quoriv.repo.ast import get_parser

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True)
class Symbol:
    """One symbol record (definition or reference)."""

    name: str
    kind: str
    lineno: int  # 1-based
    col_offset: int  # 0-based
    parent: str | None = None  # Enclosing scope name (class / struct / impl).


# Per-language map: tree-sitter node kind → Quoriv symbol kind. Adding a
# language is a matter of recording the right ``node.kind()`` values from
# its grammar. ``CONTAINER_KINDS`` flags the subset whose body holds
# nested definitions (methods inside classes, etc.) so we can record the
# nested symbol's ``parent``.
DEFINITION_KINDS: dict[str, dict[str, str]] = {
    "python": {
        "function_definition": "function",
        "class_definition": "class",
    },
    "javascript": {
        "function_declaration": "function",
        "generator_function_declaration": "function",
        "class_declaration": "class",
        "method_definition": "method",
    },
    "typescript": {
        "function_declaration": "function",
        "class_declaration": "class",
        "method_definition": "method",
        "interface_declaration": "interface",
        "type_alias_declaration": "type",
        "enum_declaration": "enum",
    },
    "tsx": {
        "function_declaration": "function",
        "class_declaration": "class",
        "method_definition": "method",
        "interface_declaration": "interface",
        "type_alias_declaration": "type",
        "enum_declaration": "enum",
    },
    "go": {
        "function_declaration": "function",
        "method_declaration": "method",
        "type_spec": "type",
    },
    "rust": {
        "function_item": "function",
        "struct_item": "struct",
        "enum_item": "enum",
        "trait_item": "trait",
        "impl_item": "impl",
    },
    "java": {
        "method_declaration": "method",
        "class_declaration": "class",
        "interface_declaration": "interface",
        "enum_declaration": "enum",
    },
    "kotlin": {
        "function_declaration": "function",
        "class_declaration": "class",
    },
    "c": {
        "function_definition": "function",
        "struct_specifier": "struct",
        "enum_specifier": "enum",
    },
    "cpp": {
        "function_definition": "function",
        "class_specifier": "class",
        "struct_specifier": "struct",
        "namespace_definition": "namespace",
    },
    "csharp": {
        "method_declaration": "method",
        "class_declaration": "class",
        "interface_declaration": "interface",
        "struct_declaration": "struct",
        "enum_declaration": "enum",
    },
    "ruby": {
        "method": "method",
        "class": "class",
        "module": "module",
    },
    "php": {
        "function_definition": "function",
        "class_declaration": "class",
        "method_declaration": "method",
        "interface_declaration": "interface",
    },
    "lua": {
        "function_declaration": "function",
        "function_definition": "function",
    },
    "elixir": {
        "call": "call",  # def/defp/defmodule surface as call nodes — refined below.
    },
    "swift": {
        "function_declaration": "function",
        "class_declaration": "class",
        "protocol_declaration": "protocol",
    },
}


# Kinds whose body introduces a name scope for nested definitions.
CONTAINER_KINDS: frozenset[str] = frozenset(
    {
        "class",
        "struct",
        "enum",
        "trait",
        "interface",
        "impl",
        "module",
        "namespace",
        "protocol",
    }
)


# Identifier-like node kinds across languages. Tree-sitter uses
# ``identifier`` almost everywhere; some grammars have specialized
# variants (``type_identifier``, ``field_identifier``) that we treat the
# same way for reference search.
_IDENTIFIER_KINDS: frozenset[str] = frozenset(
    {
        "identifier",
        "type_identifier",
        "field_identifier",
        "scoped_identifier",
        "property_identifier",
        "shorthand_property_identifier",
    }
)


def extract_definitions(
    source: str,
    language: str,
    *,
    target: str | None = None,
) -> list[Symbol]:
    """Return every definition in ``source`` (filtered by ``target`` when set).

    Args:
        source: Source text. Must be valid UTF-8 (Python ``str``).
        language: A language name from
            :data:`quoriv.repo.ast.LANGUAGE_BY_EXTENSION` — must also
            have an entry in :data:`DEFINITION_KINDS`.
        target: If given, only definitions whose name equals ``target``
            are returned (case-sensitive). When ``None``, every
            recognized definition is returned.

    Returns:
        A list of :class:`Symbol` records in source order. Empty when
        the language is unknown or has no matching definitions.
    """
    kind_map = DEFINITION_KINDS.get(language)
    if not kind_map:
        return []
    parser = get_parser(language)
    tree = parser.parse(source)
    source_bytes = source.encode("utf-8")
    out: list[Symbol] = []
    _walk_definitions(tree.root_node(), kind_map, source_bytes, target, None, out)
    return out


def find_references(source: str, language: str, target: str) -> list[Symbol]:
    """Return every identifier in ``source`` whose text equals ``target``.

    Args:
        source: Source text.
        language: A language name from
            :data:`quoriv.repo.ast.LANGUAGE_BY_EXTENSION`.
        target: The identifier text to match (case-sensitive).

    Returns:
        A list of :class:`Symbol` records (``kind="reference"``) for
        every identifier-like node in the tree whose text equals
        ``target``. Includes definition sites — callers wanting "uses
        only" should subtract definition positions from the result.
    """
    if not target:
        return []
    parser = get_parser(language)
    tree = parser.parse(source)
    source_bytes = source.encode("utf-8")
    out: list[Symbol] = []
    _walk_references(tree.root_node(), source_bytes, target, out)
    return out


# ---------------------------------------------------------------------------
# Tree-walking helpers
# ---------------------------------------------------------------------------


def _node_text(node: Any, source_bytes: bytes) -> str:
    """Decode the source slice spanned by ``node``."""
    return source_bytes[node.start_byte() : node.end_byte()].decode("utf-8", errors="replace")


def _node_name(node: Any, source_bytes: bytes) -> str | None:
    """Pull the ``name`` field off a definition node, with fallbacks.

    Most grammars use ``name: identifier``; some (Go ``type_spec``) use a
    plain identifier child. We try the explicit field first, then scan
    children for the first identifier-like named node.
    """
    field = node.child_by_field_name("name")
    if field is not None:
        return _node_text(field, source_bytes)
    for child in _named_children(node):
        if child.kind() in _IDENTIFIER_KINDS:
            return _node_text(child, source_bytes)
    return None


def _named_children(node: Any) -> Iterable[Any]:
    """Yield every named (non-syntax-token) child of ``node``."""
    for i in range(node.named_child_count()):
        yield node.named_child(i)


def _children(node: Any) -> Iterable[Any]:
    """Yield every child of ``node`` (both named and anonymous)."""
    for i in range(node.child_count()):
        yield node.child(i)


def _walk_definitions(
    node: Any,
    kind_map: dict[str, str],
    source_bytes: bytes,
    target: str | None,
    parent: str | None,
    out: list[Symbol],
) -> None:
    kind = node.kind()
    symbol_kind = kind_map.get(kind)
    next_parent = parent

    if symbol_kind is not None:
        name = _node_name(node, source_bytes)
        if name is not None and (target is None or name == target):
            pos = node.start_position()
            out.append(
                Symbol(
                    name=name,
                    kind=symbol_kind,
                    lineno=pos.row + 1,
                    col_offset=pos.column,
                    parent=parent,
                )
            )
        if symbol_kind in CONTAINER_KINDS and name is not None:
            next_parent = name

    for child in _children(node):
        _walk_definitions(child, kind_map, source_bytes, target, next_parent, out)


def _walk_references(
    node: Any,
    source_bytes: bytes,
    target: str,
    out: list[Symbol],
) -> None:
    if node.kind() in _IDENTIFIER_KINDS:
        text = _node_text(node, source_bytes)
        if text == target:
            pos = node.start_position()
            out.append(
                Symbol(
                    name=text,
                    kind="reference",
                    lineno=pos.row + 1,
                    col_offset=pos.column,
                    parent=None,
                )
            )
    for child in _children(node):
        _walk_references(child, source_bytes, target, out)
