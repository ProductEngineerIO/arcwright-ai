"""CLI application entry point — Typer app with command registration."""

from __future__ import annotations

import typer

from arcwright_ai.cli.status import init_command

app = typer.Typer(
    name="arcwright-ai",
    help="Arcwright AI — Deterministic orchestration shell for autonomous AI agent execution",
    no_args_is_help=True,
)

# Register commands
app.command(name="init")(init_command)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Arcwright AI — Deterministic orchestration shell."""
    if ctx.invoked_subcommand is None:
        raise typer.Exit()
