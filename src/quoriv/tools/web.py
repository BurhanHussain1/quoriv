"""Web tools exposed to the agent — Phase 3 Slices 6 + 7.

Phase 3 Slice 6 shipped ``web_fetch`` — a small wrapper around
:mod:`httpx` that lets the agent pull text from a URL during a turn.
Phase 3 Slice 7 adds ``web_search`` backed by Tavily — an
LLM-friendly search API with a free tier.

Design notes:

* **Sync, not async.** LangChain's ``@tool`` decorator supports
  async callables, but every other Quoriv-shipped tool is sync. The
  agent's ``ToolExecutor`` will run this in a thread pool if it
  needs to.
* **Size-bounded output.** A 50 MB HTML page would blow the model's
  context window. ``web_fetch``'s ``max_chars`` truncates with an
  explicit ``"… (truncated, +N chars)"`` marker.
* **Best-effort decoding.** ``httpx`` picks the encoding from the
  response's ``Content-Type`` header. We forward whatever it picks.
* **No JS rendering.** Plain HTTP — pages that need JS won't render.

``web_search`` requires the ``[search]`` install extra so the
``tavily-python`` SDK is available, and a ``TAVILY_API_KEY``
configured via env var or keychain. When the SDK isn't installed
or the key is missing, the tool returns a structured error dict
(matching ``web_fetch``'s contract) rather than raising — the
agent should be able to recover and try a different approach.
"""

from __future__ import annotations

import httpx
from langchain_core.tools import tool

from quoriv.config.keychain import PROVIDER_ENV_VARS, get_api_key

_DEFAULT_TIMEOUT_SECONDS = 30.0
"""Maximum time to wait for the response. Generous so slow servers
don't fail too aggressively, but bounded so a hung request can't
freeze a turn."""

_DEFAULT_MAX_CHARS = 10_000
"""Soft cap on response-body characters returned to the agent.

Roughly 2.5k-3k tokens depending on text density — comfortable for
most context windows. Override per-call via the ``max_chars``
parameter when the agent really does need the full document.
"""


@tool
def web_fetch(url: str, max_chars: int = _DEFAULT_MAX_CHARS) -> dict[str, object]:
    """Fetch a URL over HTTP and return its text body.

    Args:
        url: Absolute HTTP or HTTPS URL to fetch.
        max_chars: Soft cap on returned body length. The full body
            is truncated and the truncation is signalled in the
            return value. Defaults to 10000 (~2.5-3k tokens).

    Returns:
        A dict with:

            ``status_code``  HTTP status code (``int``).
            ``content_type`` Response ``Content-Type`` header, if any.
            ``text``         Response body decoded as text. Truncated
                             to ``max_chars`` with a
                             ``"… (truncated, +N chars)"`` suffix
                             when the body exceeds the cap.
            ``truncated``    ``True`` when the body was truncated.
            ``url``          The final URL after any redirects.

        On error (network failure, bad URL, redirect cap exceeded),
        the dict has ``"error"`` set to a short human-readable
        message and no ``status_code`` / ``text`` fields. The shape
        mirrors the git tools — every Quoriv tool returns a dict,
        and the ``"error"`` key is the universal failure signal.
    """
    try:
        with httpx.Client(
            timeout=_DEFAULT_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        # Covers connect errors, DNS failures, timeouts, redirect
        # cap exceeded, etc. — anything httpx itself reports.
        return {"error": f"HTTP error: {exc}", "url": url}
    except Exception as exc:  # pragma: no cover  # last-ditch safety net
        return {"error": f"Unexpected fetch error: {exc}", "url": url}

    body = response.text
    truncated = False
    if len(body) > max_chars:
        truncated = True
        overflow = len(body) - max_chars
        body = body[:max_chars] + f"… (truncated, +{overflow} chars)"

    return {
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type"),
        "text": body,
        "truncated": truncated,
        "url": str(response.url),
    }


# ---------------------------------------------------------------------------
# web_search — Phase 3 Slice 7
# ---------------------------------------------------------------------------


_TAVILY_PROVIDER = "tavily"
_DEFAULT_SEARCH_RESULTS = 5
"""Default number of results to return per ``web_search`` call.

Five is the sweet spot for chat-style usage: enough to triangulate a
question, few enough that the result list stays readable in the
context window. The agent can request more via ``max_results``.
"""


def _summarize_tavily_result(item: dict[str, object]) -> dict[str, object]:
    """Normalise one Tavily result row into the shape Quoriv returns.

    Tavily returns each hit with ``title`` / ``url`` / ``content`` /
    ``score`` plus optional ``raw_content``. We surface the first four
    — agents care most about the snippet + URL — and skip the heavier
    fields so the result list stays compact.
    """
    return {
        "title": item.get("title"),
        "url": item.get("url"),
        "content": item.get("content"),
        "score": item.get("score"),
    }


@tool
def web_search(
    query: str,
    max_results: int = _DEFAULT_SEARCH_RESULTS,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> dict[str, object]:
    """Search the web via Tavily and return ranked result snippets.

    Args:
        query: The natural-language search query.
        max_results: Number of results to return. Defaults to 5;
            Tavily caps at 20 per call.
        include_domains: Optional allow-list of domains. When set,
            only hits from these domains come back.
        exclude_domains: Optional deny-list of domains.

    Returns:
        A dict with:

            ``query``    The original query echoed back.
            ``results``  List of ``{title, url, content, score}``
                         dicts, ranked best-first.

        On any error (missing key, missing SDK, API failure), the
        dict has ``"error"`` set to a short human-readable message
        and no ``results`` field — same convention as
        :func:`web_fetch` and the git tools.
    """
    # Defensive import: ``tavily-python`` lives in the ``[search]``
    # install extra. A user without the extra still gets a working
    # session — just a structured error from this tool.
    try:
        from tavily import TavilyClient  # noqa: PLC0415  (intentional lazy import)
    except ImportError as exc:
        return {
            "error": (
                f"Tavily SDK not installed ({exc}). "
                f"Install Quoriv with the [search] extra to enable web_search."
            ),
            "query": query,
        }

    api_key = get_api_key(_TAVILY_PROVIDER)
    if not api_key:
        env_var = PROVIDER_ENV_VARS[_TAVILY_PROVIDER]
        return {
            "error": (
                f"No Tavily API key found. Set ${env_var} or run 'quoriv config set tavily'."
            ),
            "query": query,
        }

    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=query,
            max_results=max_results,
            include_domains=list(include_domains) if include_domains else None,
            exclude_domains=list(exclude_domains) if exclude_domains else None,
        )
    except Exception as exc:  # tavily uses bespoke exception types
        return {"error": f"Search failed: {exc}", "query": query}

    raw_results = response.get("results", []) if isinstance(response, dict) else []
    results = [_summarize_tavily_result(item) for item in raw_results if isinstance(item, dict)]
    return {"query": query, "results": results}
