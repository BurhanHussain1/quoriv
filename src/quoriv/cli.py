"""Quoriv command-line interface.

Top-level commands:

    quoriv chat                Start an interactive chat session.
    quoriv doctor              Print a health-check report.
    quoriv init                Scaffold a starter PROJECT.md for the agent.
    quoriv config show         Print the loaded configuration as JSON.
    quoriv config set X        Store an API key for provider X in the OS keychain.
    quoriv config list-providers   List known providers and which keys are set.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from rich.table import Table

if TYPE_CHECKING:
    from rich.console import Console

from quoriv import __version__
from quoriv.config import (
    PROVIDER_ENV_VARS,
    QuorivConfig,
    get_api_key,
    list_known_providers,
    load_config,
    set_api_key,
)

app = typer.Typer(
    name="quoriv",
    help="Open-source terminal AI coding agent.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
config_app = typer.Typer(
    name="config",
    help="Manage Quoriv configuration and API keys.",
    no_args_is_help=True,
)
app.add_typer(config_app)


def _console() -> Console:
    """Return a fresh Rich console honoring the configured theme.

    Returning a fresh instance per call rather than using a module-level
    singleton keeps tests from picking up output captured between cases.
    Theme resolution (Phase 3 Slice 8) reads ``config.ui.theme`` — lazy
    import to avoid loading the full config tree on commands that don't
    need it (e.g. ``quoriv version``).
    """
    from quoriv.ui.themes import make_console  # noqa: PLC0415  (intentional lazy import)

    try:
        theme = load_config().ui.theme
    except Exception:  # pragma: no cover  # malformed config — fall back
        theme = "auto"
    return make_console(theme)


# ---------------------------------------------------------------------------
# Top-level commands
# ---------------------------------------------------------------------------


@app.command()
def version() -> None:
    """Print the installed Quoriv version."""
    typer.echo(__version__)


@app.command()
def chat(
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Override the configured default model."),
    ] = None,
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            help="Permission mode for this session: read-only | ask | auto | yolo.",
        ),
    ] = "ask",
    cwd: Annotated[
        Path | None,
        typer.Option(
            "--cwd",
            help="Repository root the agent operates in. Defaults to the current directory.",
            file_okay=False,
            dir_okay=True,
            exists=True,
            resolve_path=True,
        ),
    ] = None,
) -> None:
    """Start an interactive chat session."""
    # Import here so ``quoriv --help`` doesn't pay the prompt_toolkit / Rich
    # / langchain-openai / deepagents import cost.
    from quoriv.app import run_chat  # noqa: PLC0415  (intentional lazy import)

    cfg = load_config()
    asyncio.run(run_chat(cfg, model_override=model, mode=mode, cwd=cwd))


@app.command()
def replay(
    target: Annotated[
        str,
        typer.Argument(
            help=(
                "Saved session name or raw thread id. Names are resolved "
                "via the per-cwd session registry; raw ids look up the "
                "trace file directly."
            ),
        ),
    ],
    cwd: Annotated[
        Path | None,
        typer.Option(
            "--cwd",
            help="Repository root holding the .quoriv/traces directory. Defaults to cwd.",
            file_okay=False,
            dir_okay=True,
            exists=True,
            resolve_path=True,
        ),
    ] = None,
) -> None:
    """Replay a saved chat session — read-only viewer over the JSONL trace.

    Phase 3 Slice 12: walks ``<cwd>/.quoriv/traces/<thread_id>.jsonl``
    and prints each event (turn_start / model_complete / tool_start /
    tool_end / turn_end) with a Rich-formatted prefix. No model is
    invoked; no tool is executed.
    """
    from quoriv.core import SessionRegistry, trace_path  # noqa: PLC0415
    from quoriv.replay import replay_thread  # noqa: PLC0415

    console = _console()
    root = cwd if cwd is not None else Path.cwd()

    # First try the registry (name → thread id). Fall back to treating
    # the input as a raw thread id.
    registry = SessionRegistry.for_cwd(root)
    record = registry.load(target)
    thread_id = record.thread_id if record is not None else target
    path = trace_path(root, thread_id)
    rendered = replay_thread(console, path)
    if rendered == 0 and record is None:
        console.print(
            f"[red]No trace found for {target!r}.[/red]  "
            f"Try [cyan]/load[/cyan] in chat or pass a saved session name."
        )
        raise typer.Exit(code=1)


@app.command()
def eval(  # Typer command name maps to the user-facing `quoriv eval` subcommand
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Override the configured default model."),
    ] = None,
    cwd: Annotated[
        Path | None,
        typer.Option(
            "--cwd",
            help="Repository root the agent operates in. Defaults to the current directory.",
            file_okay=False,
            dir_okay=True,
            exists=True,
            resolve_path=True,
        ),
    ] = None,
) -> None:
    """Run the bundled eval suite against the configured model.

    Each case in :data:`quoriv.eval.SAMPLE_CASES` is driven through
    one agent turn in ``yolo`` mode (no HITL prompts) and scored via
    substring match. Prints a Rich table summarising pass / fail per
    case and exits non-zero if any case failed.
    """
    from quoriv.eval import SAMPLE_CASES, run_suite, summarize  # noqa: PLC0415

    console = _console()
    cfg = load_config()
    results = asyncio.run(
        run_suite(
            SAMPLE_CASES,
            config=cfg,
            cwd=cwd,
            model_override=model,
        )
    )

    table = Table(title="Quoriv eval results")
    table.add_column("Case", style="bold")
    table.add_column("Status")
    table.add_column("Missing")
    for result in results:
        status = "[green]pass[/green]" if result.passed else "[red]fail[/red]"
        missing = ", ".join(result.failed_substrings) if result.failed_substrings else ""
        table.add_row(result.case_name, status, missing)
    console.print(table)

    counts = summarize(results)
    console.print(
        f"[bold]{counts['passed']}/{counts['total']}[/bold] passed "
        f"([red]{counts['failed']}[/red] failed)"
    )
    if counts["failed"] > 0:
        raise typer.Exit(code=1)


@app.command()
def doctor() -> None:
    """Health check: Python version, config, API keys."""
    console = _console()
    cfg = load_config()
    table = _build_doctor_table(cfg)
    console.print(table)


@app.command()
def init(
    path: Annotated[
        Path | None,
        typer.Argument(
            help="Directory to scaffold PROJECT.md into. Defaults to the current directory.",
            file_okay=False,
            dir_okay=True,
            exists=True,
            resolve_path=True,
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Overwrite an existing PROJECT.md instead of refusing.",
        ),
    ] = False,
) -> None:
    """Scaffold a starter ``PROJECT.md`` for the agent.

    ``PROJECT.md`` is one of the two files Quoriv hands to DeepAgents'
    ``MemoryMiddleware`` at session start (the other is
    ``~/.quoriv/memory.md``). This command writes a short starter
    template so users can fill in the high-signal context the agent
    should see — project overview, conventions, useful commands.

    Refuses to overwrite by default. Pass ``--force`` to replace an
    existing file.
    """
    # Imported here to keep the help-text path free of the rest of
    # the package — same pattern as the lazy ``run_chat`` import in
    # ``chat``.
    from quoriv.core.memory import (  # noqa: PLC0415  (intentional lazy import)
        PROJECT_MEMORY_FILENAME,
        PROJECT_MEMORY_TEMPLATE,
    )

    console = _console()
    target_dir = path if path is not None else Path.cwd()
    target = target_dir / PROJECT_MEMORY_FILENAME

    existed_before = target.exists()
    if existed_before and not force:
        console.print(f"[yellow]{target} already exists.[/yellow]")
        console.print("Pass [cyan]--force[/cyan] to overwrite.")
        raise typer.Exit(code=1)

    target.write_text(PROJECT_MEMORY_TEMPLATE, encoding="utf-8")
    verb = "Overwrote" if existed_before else "Created"
    console.print(f"[green]{verb}[/green] {target}")
    console.print("[dim]Edit it to point the agent at the context that matters most.[/dim]")


def _build_doctor_table(cfg: QuorivConfig) -> Table:
    """Construct the Rich table rendered by ``quoriv doctor``."""
    table = Table(title=f"Quoriv {__version__}")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Detail")

    table.add_row("Python", "[green]ok[/green]", sys.version.split()[0])
    table.add_row("Default model", "[green]ok[/green]", cfg.model.default)
    table.add_row("Fast model", "[green]ok[/green]", cfg.model.fast)
    table.add_row("Strong model", "[green]ok[/green]", cfg.model.strong)
    table.add_row("Permission mode", "[green]ok[/green]", cfg.permissions.mode)
    table.add_row("UI theme", "[green]ok[/green]", cfg.ui.theme)

    for provider in list_known_providers():
        env_var = PROVIDER_ENV_VARS[provider]
        key = get_api_key(provider)
        if key:
            source = "env" if os.environ.get(env_var) else "keychain"
            table.add_row(f"{provider} key", "[green]ok[/green]", f"found ({source})")
        else:
            table.add_row(
                f"{provider} key",
                "[yellow]missing[/yellow]",
                f"set ${env_var} or 'quoriv config set {provider}'",
            )

    return table


# ---------------------------------------------------------------------------
# config subcommands
# ---------------------------------------------------------------------------


@config_app.command("show")
def config_show() -> None:
    """Print the loaded configuration as JSON."""
    cfg = load_config()
    _console().print_json(cfg.model_dump_json())


@config_app.command("set")
def config_set(
    provider: Annotated[str, typer.Argument(help="Provider name (e.g. openai)")],
) -> None:
    """Store an API key for ``provider`` in the OS keychain.

    Prompts for the key with hidden input. Keys are written to the OS
    keychain via the ``keyring`` library — never to disk in plaintext.
    """
    console = _console()
    if provider not in list_known_providers():
        console.print(f"[red]Unknown provider: {provider!r}[/red]")
        console.print(f"Known providers: {', '.join(list_known_providers())}")
        raise typer.Exit(code=1)

    key = typer.prompt(
        f"Enter API key for {provider}",
        hide_input=True,
        confirmation_prompt=False,
    ).strip()

    if not key:
        console.print("[red]Empty key; aborting.[/red]")
        raise typer.Exit(code=1)

    set_api_key(provider, key)
    console.print(f"[green]Saved {provider} API key to keychain.[/green]")


@config_app.command("list-providers")
def config_list_providers() -> None:
    """List known providers and whether a key is configured."""
    console = _console()
    table = Table(title="Known providers")
    table.add_column("Provider", style="bold")
    table.add_column("Env var")
    table.add_column("Key configured")

    for provider in list_known_providers():
        env_var = PROVIDER_ENV_VARS[provider]
        configured = "[green]yes[/green]" if get_api_key(provider) else "[dim]no[/dim]"
        table.add_row(provider, env_var, configured)

    console.print(table)


# ---------------------------------------------------------------------------
# Entry point hook (referenced by pyproject.toml [project.scripts])
# ---------------------------------------------------------------------------


def main() -> None:
    """Programmatic entry equivalent to running the ``quoriv`` console script."""
    app()
