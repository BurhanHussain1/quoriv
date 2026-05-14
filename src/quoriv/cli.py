"""Quoriv command-line interface.

Top-level commands:

    quoriv chat                Start an interactive chat session.
    quoriv doctor              Print a health-check report.
    quoriv config show         Print the loaded configuration as JSON.
    quoriv config set X        Store an API key for provider X in the OS keychain.
    quoriv config list-providers   List known providers and which keys are set.

For Phase 0 Day 4, ``chat`` streams responses directly from the configured
LLM (no DeepAgents integration yet — that lands in Day 5).
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

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
    """Return a fresh Rich console.

    Returning a fresh instance per call rather than using a module-level
    singleton keeps tests from picking up output captured between cases.
    """
    return Console()


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
) -> None:
    """Start an interactive chat session."""
    # Import here so ``quoriv --help`` doesn't pay the prompt_toolkit / Rich
    # / langchain-openai import cost.
    from quoriv.app import run_chat  # noqa: PLC0415  (intentional lazy import)

    cfg = load_config()
    asyncio.run(run_chat(cfg, model_override=model, mode=mode))


@app.command()
def doctor() -> None:
    """Health check: Python version, config, API keys."""
    console = _console()
    cfg = load_config()
    table = _build_doctor_table(cfg)
    console.print(table)


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
