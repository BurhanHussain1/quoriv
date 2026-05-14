"""Symbol-search tool — Quoriv's first language-aware tool.

Phase 1 Slice 4 ships a minimal **Python-only** ``find_symbol`` using the
standard-library ``ast`` module. Full multi-language tree-sitter support
(``go_to_definition``, ``find_references``, JS/TS/Go/Rust/...) lands in
Slice 4b once the ``tree-sitter`` and ``tree-sitter-languages`` extras
are installed.

The tool is a plain ``@tool``-decorated callable, passed to
``create_deep_agent(tools=[...])``. It runs against the actual filesystem
under the chat session's working directory.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

_KIND_BY_NODE: dict[type[ast.AST], str] = {
    ast.FunctionDef: "function",
    ast.AsyncFunctionDef: "async_function",
    ast.ClassDef: "class",
}


def _walk_symbols(
    tree: ast.AST,
    target: str,
    *,
    parent: str = "",
) -> list[dict[str, Any]]:
    """Yield matching symbol records from a parsed Python AST."""
    matches: list[dict[str, Any]] = []
    for node in ast.iter_child_nodes(tree):
        # Function / class definitions
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
            # Recurse into class bodies so methods (one level of nesting) are found.
            if isinstance(node, ast.ClassDef):
                matches.extend(_walk_symbols(node, target, parent=node.name))
        # Module/class-level assignments: `target = ...`
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


def _scan_file(file: Path, target: str) -> list[dict[str, Any]]:
    """Parse one ``.py`` file and return symbol matches with ``file=`` set."""
    try:
        source = file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source, filename=str(file))
    except SyntaxError:
        return []
    matches = _walk_symbols(tree, target)
    for m in matches:
        m["file"] = str(file)
    return matches


@tool
def find_symbol(name: str, path: str = ".") -> list[dict[str, Any]]:
    """Find Python definitions (function / class / module-level variable) of a symbol.

    Walks ``*.py`` files under ``path`` and returns every definition whose
    name matches ``name`` exactly (case-sensitive).

    Args:
        name: The symbol name to search for, e.g. ``"build_agent"``.
        path: Directory (relative or absolute) to search. Defaults to the
            current working directory.

    Returns:
        A list of records, each describing one matching definition:
        ``{"file": str, "lineno": int, "col_offset": int, "kind": str,
        "name": str, "parent": str | None}``. Empty list when nothing matches.

        ``kind`` is one of ``"function"``, ``"async_function"``, ``"class"``,
        ``"variable"``. ``parent`` is the enclosing class name for methods,
        otherwise ``None``.

    Limitation:
        Python only in Slice 4. Use ``grep`` for symbols in JS/Go/Rust/etc.
        until Slice 4b lands.
    """
    root = Path(path).expanduser()
    if not root.exists():
        return []
    matches: list[dict[str, Any]] = []
    files = [root] if root.is_file() else list(root.rglob("*.py"))
    for file in files:
        # Skip common virtualenv / build noise so we don't return matches
        # from third-party packages.
        parts = file.parts
        if any(p in {".venv", "venv", "__pycache__", ".git", "build", "dist"} for p in parts):
            continue
        matches.extend(_scan_file(file, name))
    return matches
