"""Built-in tools the agent can call.

Every tool is wrapped through the permission system before execution.
Tools are grouped by category:

    files       read, write, edit, multi_edit, ls, glob.
    search      grep, file_glob.
    ast_tools   tree-sitter symbol lookup and references.
    shell       execute, kill, background.
    git         status, diff, log, commit, blame.
    tests       language-aware test runner.
    web         search, fetch.
    patch       safe unified-diff apply.
"""
