"""Quoriv — open-source terminal AI coding agent.

Quoriv is a Python-built coding agent that lives in your terminal and works
directly inside your repository. It is model-agnostic (OpenAI, Anthropic,
Gemini, Ollama, vLLM), built on DeepAgents + LangGraph, and Apache 2.0
licensed.

See https://github.com/BurhanHussain1/quoriv for details.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("quoriv")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
