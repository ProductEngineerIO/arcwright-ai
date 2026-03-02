"""CLI application entry point — Typer app with command registration."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="arcwright-ai",
    help="Arcwright AI — Deterministic orchestration shell for autonomous AI agent execution",
    no_args_is_help=True,
)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        raise typer.Exit()
