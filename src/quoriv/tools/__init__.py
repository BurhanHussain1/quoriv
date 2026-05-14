"""Quoriv-specific tools, layered on top of DeepAgents' built-ins.

DeepAgents already provides the standard file and shell tools through
``FilesystemMiddleware`` and ``SandboxBackendProtocol``:

    ls, read_file, write_file, edit_file, glob, grep,    (built into DeepAgents)
    execute, task, write_todos                            (built into DeepAgents)

This package contains the tools DeepAgents does **not** ship — registered as
plain callables and passed to ``create_deep_agent`` via ``tools=[...]``.

Modules (implemented in Phase 1 / Phase 3):
    ast_tools   tree-sitter symbol lookup: find_symbol, go_to_definition,
                find_references.
    git         status, diff, log, commit, blame. Write ops are gated by
                ``interrupt_on={"git_commit": True}`` when in ``ask``/``auto``
                mode.
    tests       Language-aware test runner: pytest / jest / cargo test /
                go test, detected from the repo.
    web         web_search and web_fetch (Phase 3).

What's **not** here, and why:

    - No ``files.py`` / ``read``/``write``/``edit`` — DeepAgents owns these.
    - No ``search.py`` / ``grep`` — DeepAgents owns this (literal substring;
      add a ``regex_grep`` tool here if regex is needed later).
    - No ``shell.py`` / ``execute`` — ``LocalShellBackend`` owns this.
    - No ``patch.py`` — use DeepAgents' ``edit_file``.
    - No ``base.py`` — use ``langchain_core.tools.tool`` decorator directly.
"""
