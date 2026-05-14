"""Tree-sitter parsing layer that powers Quoriv's AST tools.

DeepAgents' built-in ``glob`` and ``grep`` cover lightweight repo
enumeration and literal-substring search. Quoriv adds symbol-aware
navigation on top via tree-sitter — this package is the implementation
detail that backs the tools in ``quoriv.tools.ast_tools``.

Modules (implemented in Phase 1):
    ast         Per-language tree-sitter parser registry (Python, JS/TS,
                Go, Rust, Java, C/C++, Ruby, ... — ~30 languages).
    symbols     Symbol lookup index built lazily from parsed trees:
                find_symbol(name), find_definition(name),
                find_references(name).

No embeddings, no LSP. Phase 1 stays with grep + AST for the best
quality-per-effort ratio.

What's **not** here, and why:

    - No generic ``index.py`` — DeepAgents' ``glob`` covers file enumeration.
"""
