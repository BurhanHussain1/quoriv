"""Web tools exposed to the agent — Phase 3 Slice 6.

Phase 3 Slice 6 ships ``web_fetch`` — a small wrapper around
:mod:`httpx` that lets the agent pull text from a URL during a turn.
A future slice adds ``web_search`` once we pick a backend (Tavily,
SerpAPI, Brave, …); doing the fetch tool first keeps this slice
self-contained and free of new API-key dependencies.

Design notes:

* **Sync, not async.** LangChain's ``@tool`` decorator supports
  async callables, but every other Quoriv-shipped tool is sync. The
  agent's ``ToolExecutor`` will run this in a thread pool if it
  needs to.
* **Size-bounded output.** A 50 MB HTML page would blow the model's
  context window. ``max_chars`` truncates the returned text with an
  explicit ``"… (truncated, +N chars)"`` marker so the agent knows
  more content exists.
* **Best-effort decoding.** ``httpx`` picks the encoding from the
  response's ``Content-Type`` header. We forward whatever it picks
  rather than guessing.
* **No JS rendering.** This is plain HTTP — the agent can't fetch
  pages that need JS to render. A separate slice could wire a
  headless browser if needed.
"""

from __future__ import annotations

import httpx
from langchain_core.tools import tool

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
