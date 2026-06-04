"""Agent progress notifications — decoupled from CLI (DIP)."""
from __future__ import annotations

from cli.ui_context import is_quiet_console, notify_progress


def agent_note(message: str, *, also_print: bool = False) -> None:
    """Log agent activity; routes to Live UI status when quiet mode is on."""
    plain = _strip_rich(message)
    if is_quiet_console():
        notify_progress(plain)
        return
    if also_print:
        from rich.console import Console

        Console().print(message)


def _strip_rich(text: str) -> str:
    return (
        text.replace("[bold]", "")
        .replace("[/bold]", "")
        .replace("[cyan]", "")
        .replace("[/cyan]", "")
        .replace("[green]", "")
        .replace("[/green]", "")
        .replace("[dim]", "")
        .replace("[/dim]", "")
        .replace("\n", " ")
        .strip()
    )
