"""Symbol-search tools — Phase 1 Slice 4 + 4b.

Slice 4 shipped ``find_symbol`` against Python source via the stdlib
``ast`` module (no tree-sitter dependency). Slice 4b expands the surface:

    find_symbol(name, path=".")              Multi-language — walks the path,
                                             dispatches to stdlib ``ast`` for
                                             ``.py`` files and tree-sitter
                                             for every other supported
                                             extension.
    go_to_definition(name, path=".")         Strict alias of ``find_symbol``;
                                             named for the agent's mental
                                             model ("jump to the definition
                                             of X").
    find_references(name, path=".")          Every identifier match — call
                                             sites, type uses, field
                                             accesses, definitions.

Tree-sitter parsing lives in :mod:`quoriv.repo.ast` and
:mod:`quoriv.repo.symbols` — those modules return uniform
:class:`~quoriv.repo.symbols.Symbol` records that we serialize into the
LangChain ``@tool`` ``dict[str, Any]`` schema here. When the ``ast``
extra is not installed (``pip install 'quoriv[ast]'``) the tools fall
back gracefully: Python files still resolve via the stdlib, non-Python
files return empty.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from quoriv.repo.ast import detect_language, is_available
from quoriv.repo.symbols import (
    DEFINITION_KINDS,
    Symbol,
    extract_definitions,
)
from quoriv.repo.symbols import (
    find_references as _ts_find_references,
)

_KIND_BY_NODE: dict[type[ast.AST], str] = {
    ast.FunctionDef: "function",
    ast.AsyncFunctionDef: "async_function",
    ast.ClassDef: "class",
}


# Directories we never descend into during repo-walk searches.
_SKIP_DIRS: frozenset[str] = frozenset(
    {".venv", "venv", "__pycache__", ".git", "build", "dist", "node_modules", "target"}
)


# ---------------------------------------------------------------------------
# Stdlib-Python extractor (Slice 4 original code, unchanged in behavior).
# ---------------------------------------------------------------------------


def _walk_python_symbols(
    tree: ast.AST,
    target: str,
    *,
    parent: str = "",
) -> list[dict[str, Any]]:
    """Yield matching symbol records from a parsed Python AST."""
    matches: list[dict[str, Any]] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == target:
                matches.append(
                    {
                        "kind": _KIND_BY_NODE[type(node)],
                        "name": target,
                        "lineno": node.lineno,
                        "col_offset": node.col_offset,
                        "parent": parent or None,
                    }
                )
            if isinstance(node, ast.ClassDef):
                matches.extend(_walk_python_symbols(node, target, parent=node.name))
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == target:
                    matches.append(
                        {
                            "kind": "variable",
                            "name": target,
                            "lineno": node.lineno,
                            "col_offset": node.col_offset,
                            "parent": parent or None,
                        }
                    )
    return matches


def _scan_python_file(file: Path, target: str) -> list[dict[str, Any]]:
    """Parse one ``.py`` file with stdlib ``ast`` and return symbol matches."""
    try:
        source = file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source, filename=str(file))
    except SyntaxError:
        return []
    matches = _walk_python_symbols(tree, target)
    for m in matches:
        m["file"] = str(file)
    return matches


# ---------------------------------------------------------------------------
# Tree-sitter helpers (multi-language).
# ---------------------------------------------------------------------------


def _symbol_to_dict(symbol: Symbol, file: str) -> dict[str, Any]:
    return {
        "file": file,
        "lineno": symbol.lineno,
        "col_offset": symbol.col_offset,
        "kind": symbol.kind,
        "name": symbol.name,
        "parent": symbol.parent,
    }


def _scan_with_tree_sitter(
    file: Path,
    target: str | None,
    *,
    mode: str,
) -> list[dict[str, Any]]:
    """Scan one file with tree-sitter.

    Args:
        file: Source file. ``detect_language`` is called on its name.
        target: Symbol name to filter by; ``None`` returns every
            definition (only valid when ``mode == "definitions"``).
        mode: Either ``"definitions"`` or ``"references"``.

    Returns:
        Serialized symbol records. Empty when the file's language is
        unknown, the ``ast`` extra is not installed, or the file fails
        to decode.
    """
    if not is_available():
        return []
    language = detect_language(file)
    if language is None or language not in DEFINITION_KINDS:
        return []
    try:
        source = file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        if mode == "definitions":
            symbols = extract_definitions(source, language, target=target)
        else:
            if target is None:
                return []
            symbols = _ts_find_references(source, language, target)
    except Exception:  # tree-sitter / language pack bubbles up many types
        return []
    return [_symbol_to_dict(s, str(file)) for s in symbols]


def _iter_source_files(root: Path) -> list[Path]:
    """Walk ``root`` and yield every file with a supported extension.

    Skips common build / vendor directories listed in :data:`_SKIP_DIRS`.
    """
    if root.is_file():
        return [root]
    out: list[Path] = []
    for file in root.rglob("*"):
        if not file.is_file():
            continue
        if any(p in _SKIP_DIRS for p in file.parts):
            continue
        if file.suffix.lower() == ".py" or detect_language(file) is not None:
            out.append(file)
    return out


def _walk_definitions(root: Path, target: str | None) -> list[dict[str, Any]]:
    """Collect definitions across every supported file under ``root``."""
    matches: list[dict[str, Any]] = []
    for file in _iter_source_files(root):
        if file.suffix.lower() in {".py", ".pyi"}:
            if target is None:
                # ``find_symbol`` always filters by name; this path is
                # unreachable from the public tools, but defend the
                # invariant anyway.
                continue
            matches.extend(_scan_python_file(file, target))
        else:
            matches.extend(_scan_with_tree_sitter(file, target, mode="definitions"))
    return matches


# ---------------------------------------------------------------------------
# Public @tool surface.
# ---------------------------------------------------------------------------


@tool
def find_symbol(name: str, path: str = ".") -> list[dict[str, Any]]:
    """Find definitions of a symbol across all supported languages under ``path``.

    Python files (``.py`` / ``.pyi``) use the stdlib ``ast`` module so
    they always work even without the ``ast`` extra installed. Every
    other supported extension routes through tree-sitter via
    :mod:`quoriv.repo.symbols`.

    Args:
        name: The symbol name to search for, case-sensitive.
        path: File or directory (relative or absolute) to search.
            Defaults to the current working directory.

    Returns:
        A list of records, each:
        ``{"file": str, "lineno": int, "col_offset": int, "kind": str,
        "name": str, "parent": str | None}``. Empty list when nothing
        matches. ``kind`` varies by language (function / class / method /
        struct / trait / interface / type / enum / variable).
    """
    root = Path(path).expanduser()
    if not root.exists():
        return []
    return _walk_definitions(root, name)


@tool
def go_to_definition(name: str, path: str = ".") -> list[dict[str, Any]]:
    """Locate the definition site(s) of a symbol — same shape as ``find_symbol``.

    A semantic alias for the agent's "jump to definition" intent.
    Behavior is identical to :func:`find_symbol`; the separate tool name
    helps the LLM pick the right verb when planning navigation steps.

    Args:
        name: The symbol name to locate.
        path: File or directory to search.

    Returns:
        Same shape as :func:`find_symbol`.
    """
    root = Path(path).expanduser()
    if not root.exists():
        return []
    return _walk_definitions(root, name)


@tool
def find_references(name: str, path: str = ".") -> list[dict[str, Any]]:
    """Find every reference to a symbol across supported languages under ``path``.

    A "reference" here is any identifier-like node in the syntax tree
    whose text equals ``name``. That includes:

        - definition sites (the ``def foo(): ...`` line itself)
        - call sites (``foo()``)
        - type uses (``x: Foo``)
        - field accesses (``obj.foo``)

    Args:
        name: The identifier to search for.
        path: File or directory to search.

    Returns:
        A list of records:
        ``{"file": str, "lineno": int, "col_offset": int, "kind": str,
        "name": str, "parent": str | None}``. ``kind`` is always
        ``"reference"`` for tree-sitter-backed hits; Python files
        (``.py`` / ``.pyi``) currently return only definitions matching
        the name, because reference search there needs a richer walker
        (deferred to a later slice).
    """
    if not name:
        return []
    root = Path(path).expanduser()
    if not root.exists():
        return []
    matches: list[dict[str, Any]] = []
    for file in _iter_source_files(root):
        if file.suffix.lower() in {".py", ".pyi"}:
            matches.extend(_scan_python_file(file, name))
        else:
            matches.extend(_scan_with_tree_sitter(file, name, mode="references"))
    return matches
