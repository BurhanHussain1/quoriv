"""Language detection + tree-sitter parser registry — Phase 1 Slice 4b.

Built on top of :pkg:`tree_sitter_language_pack` (bundled wheels for ~80
languages on Python 3.10-3.13). This module gives the rest of Quoriv a
**stable, narrow API** over that pack:

    detect_language(path)       → language name or None
    get_parser(language)        → tree_sitter_language_pack.Parser
    is_available()              → bool — True iff the ``ast`` extra is installed

The ``tree-sitter`` + ``tree-sitter-language-pack`` dependencies live in
the ``ast`` optional-extras group (``pip install -e ".[ast]"``). Callers
that don't install the extra still get :func:`is_available` returning
``False`` and graceful ``None`` returns from :func:`detect_language` —
nothing in this module raises on a missing extra at import time.

We deliberately keep the language set explicit rather than letting the
pack auto-detect *everything*: an extension we haven't tested means an
extraction query we haven't validated. Adding a language is a two-line
change in :data:`LANGUAGE_BY_EXTENSION` plus a kind map in
:mod:`quoriv.repo.symbols`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


# File-extension → tree-sitter language name. Names match exactly what
# :func:`tree_sitter_language_pack.get_parser` accepts (lowercased, no
# leading dot). When a language has multiple common extensions we list
# all of them.
LANGUAGE_BY_EXTENSION: dict[str, str] = {
    # Python
    ".py": "python",
    ".pyi": "python",
    # JavaScript / TypeScript
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    # Go
    ".go": "go",
    # Rust
    ".rs": "rust",
    # Java / Kotlin / Scala
    ".java": "java",
    ".kt": "kotlin",
    ".scala": "scala",
    # C / C++ / C#
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".cs": "csharp",
    # Ruby / PHP / Perl
    ".rb": "ruby",
    ".php": "php",
    ".pl": "perl",
    # Shell / scripting
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    # Web / config languages
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
    # Lua / Elixir / Erlang / Haskell / OCaml / Swift / Dart
    ".lua": "lua",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hs": "haskell",
    ".ml": "ocaml",
    ".swift": "swift",
    ".dart": "dart",
    # SQL / R / Julia / Zig / Nim
    ".sql": "sql",
    ".r": "r",
    ".jl": "julia",
    ".zig": "zig",
    ".nim": "nim",
}


def is_available() -> bool:
    """Return True iff the ``tree_sitter_language_pack`` extra is installed."""
    try:
        import tree_sitter_language_pack  # noqa: F401, PLC0415  (lazy probe)
    except ImportError:
        return False
    return True


def detect_language(path: Path | str) -> str | None:
    """Return the tree-sitter language name inferred from ``path``'s extension.

    Args:
        path: Filesystem path. Only the suffix (case-insensitive) is
            consulted; the file does not need to exist.

    Returns:
        The language name (e.g. ``"python"``, ``"javascript"``, ``"go"``)
        or ``None`` when the extension is not in
        :data:`LANGUAGE_BY_EXTENSION`.
    """
    suffix = str(path).rsplit(".", 1)
    if len(suffix) != 2:
        return None
    ext = "." + suffix[1].lower()
    return LANGUAGE_BY_EXTENSION.get(ext)


def get_parser(language: str) -> Any:
    """Return a tree-sitter ``Parser`` for ``language``.

    Args:
        language: A language name that appears in
            :data:`LANGUAGE_BY_EXTENSION` (e.g. ``"python"``).

    Returns:
        A ``tree_sitter_language_pack.Parser`` instance.

    Raises:
        RuntimeError: If the ``ast`` extra is not installed.
        LookupError: If ``language`` is unknown to the language pack.
    """
    try:
        from tree_sitter_language_pack import get_parser as _get_parser  # noqa: PLC0415
    except ImportError as exc:
        msg = (
            "Tree-sitter parsers are not installed. Install Quoriv with the "
            "'ast' extra: pip install 'quoriv[ast]'."
        )
        raise RuntimeError(msg) from exc
    try:
        return _get_parser(language)
    except Exception as exc:
        raise LookupError(f"No tree-sitter parser for language {language!r}") from exc
