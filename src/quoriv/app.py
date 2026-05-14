"""Interactive chat loop — Phase 0 Day 4.

Streams responses directly from the configured LLM. **No DeepAgents
integration yet** — Day 5 adds it. This slice exists to prove the UI loop
works in isolation before we plug the agent in.

Architecture:
    * Rich `Console` for output rendering.
    * `prompt_toolkit.PromptSession` for input (multi-line support, history).
    * LangChain `BaseChatModel.astream(messages)` for token streaming.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, HumanMessage
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.panel import Panel

from quoriv import __version__
from quoriv.models import MissingAPIKeyError, get_model

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import BaseMessage

    from quoriv.config import QuorivConfig


SLASH_COMMANDS: dict[str, str] = {
    "/help": "List available slash commands",
    "/clear": "Clear the conversation",
    "/exit": "Exit the chat session",
    "/quit": "Exit the chat session (alias)",
}


async def run_chat(
    config: QuorivConfig,
    *,
    model_override: str | None = None,
    mode: str = "ask",
) -> None:
    """Run the interactive chat loop until the user exits.

    Args:
        config: Loaded Quoriv configuration.
        model_override: Optional ``provider:name`` string overriding
            ``config.model.default`` for this session.
        mode: Permission mode label (only displayed in the welcome banner
            for Day 4; Phase 1 wires this into DeepAgents ``permissions=``
            and ``interrupt_on=`` config).
    """
    console = Console()
    model_id = model_override or config.model.default

    try:
        model = get_model(model_id)
    except MissingAPIKeyError as exc:
        _render_missing_key(console, exc)
        return
    except Exception as exc:  # pragma: no cover  # surfaces upstream errors
        console.print(f"[red]Failed to load model {model_id!r}:[/red] {exc}")
        return

    _render_welcome(console, model_id, mode)

    history: list[BaseMessage] = []
    session: PromptSession[str] = PromptSession()

    while True:
        try:
            user_input = await session.prompt_async(HTML("<ansigreen>></ansigreen> "))
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            return

        user_input = user_input.strip()
        if not user_input:
            continue

        if user_input.startswith("/"):
            if _handle_slash(console, user_input, history):
                continue
            return  # /exit or /quit

        history.append(HumanMessage(content=user_input))
        try:
            assistant_text = await _stream_response(console, model, history)
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted.[/yellow]")
            history.pop()  # drop the unanswered prompt
            continue
        except Exception as exc:  # surface model/network errors gracefully
            console.print(f"\n[red]Error from model:[/red] {exc}")
            history.pop()
            continue

        history.append(AIMessage(content=assistant_text))


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _render_welcome(console: Console, model_id: str, mode: str) -> None:
    console.print(
        Panel.fit(
            (
                f"[bold]Quoriv[/bold] v{__version__}\n"
                f"Model: [cyan]{model_id}[/cyan]\n"
                f"Mode:  [cyan]{mode}[/cyan]\n"
                f"Type [yellow]/help[/yellow] for commands, [yellow]/exit[/yellow] to quit."
            ),
            title="welcome",
            border_style="cyan",
        )
    )


def _render_missing_key(console: Console, exc: MissingAPIKeyError) -> None:
    console.print(f"\n[red]No API key found for provider {exc.provider!r}.[/red]\n")
    console.print("Configure one of the following:")
    console.print(f"  • Run:    [cyan]quoriv config set {exc.provider}[/cyan]")
    console.print(f"  • Or set: [cyan]${exc.env_var}=<your-key>[/cyan] in the environment\n")


def _handle_slash(
    console: Console,
    raw: str,
    history: list[BaseMessage],
) -> bool:
    """Dispatch a slash command.

    Returns:
        ``True`` if the loop should continue, ``False`` if the user asked
        to exit.
    """
    cmd = raw.split(maxsplit=1)[0].lower()

    if cmd in ("/exit", "/quit"):
        console.print("[dim]Goodbye.[/dim]")
        return False

    if cmd == "/clear":
        history.clear()
        console.clear()
        console.print("[dim]Conversation cleared.[/dim]")
        return True

    if cmd == "/help":
        console.print()
        for c, desc in SLASH_COMMANDS.items():
            console.print(f"  [cyan]{c:<8}[/cyan]  {desc}")
        console.print()
        return True

    console.print(f"[red]Unknown command:[/red] {cmd}  (try [cyan]/help[/cyan])")
    return True


async def _stream_response(
    console: Console,
    model: BaseChatModel,
    history: list[BaseMessage],
) -> str:
    """Stream a response from ``model`` and accumulate the assistant text.

    For Day 4 the streaming renderer prints plain text without re-parsing
    as markdown. Phase 1 replaces this with a proper streaming markdown
    renderer (Rich ``Live`` widget) and syntax-highlighted code blocks.
    """
    parts: list[str] = []
    console.print()

    async for chunk in model.astream(history):
        text = _chunk_text(chunk.content)
        if text:
            console.out(text, end="", highlight=False)
            parts.append(text)

    console.print()  # newline after streaming completes
    return "".join(parts)


def _chunk_text(content: str | list[str | dict[str, object]]) -> str:
    """Extract plain text from a LangChain message chunk's content.

    Most chunks have a string content; some (multimodal, tool-use) carry
    a list of content blocks. We surface only the text blocks here.
    """
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text", "")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)
