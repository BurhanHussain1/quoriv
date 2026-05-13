"""Repository understanding.

Combines lightweight grep/glob with tree-sitter AST parsing to give the
agent symbol-aware navigation: find_symbol, go_to_definition, find_references.

No embeddings, no LSP. Phase 1 stays with grep + AST for the best
quality-per-effort ratio.
"""
