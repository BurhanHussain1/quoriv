# Architecture

Quoriv is a thin shell around [DeepAgents](https://github.com/langchain-ai/deepagents) + [LangGraph](https://github.com/langchain-ai/langgraph). The runtime is DeepAgents; Quoriv supplies the CLI/TUI, configuration, keychain, model factory, permission modes, AST/git/tests/web tools, hooks, eval harness, and MCP/plugin loaders.

The full DeepAgents integration reference — every feature Quoriv builds on, the LangGraph state model, middleware ordering, checkpointer semantics, and the exact mapping from Quoriv permission modes to DeepAgents `interrupt_on=` dicts — lives in [`DEEPAGENTS_REFERENCE.md`](DEEPAGENTS_REFERENCE.md).

{%
    include-markdown "./DEEPAGENTS_REFERENCE.md"
    rewrite-relative-urls=true
%}
