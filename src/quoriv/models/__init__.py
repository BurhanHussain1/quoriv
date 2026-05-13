"""Model provider abstraction.

Wraps LangChain chat models behind a uniform interface so the agent can
swap between OpenAI, Anthropic, Google Gemini, Ollama, vLLM, and OpenRouter
without code changes.

Phase 1: OpenAI provider only.
Phase 3: All other providers.
"""
