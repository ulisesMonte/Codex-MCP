"""Agent logging that respects Live UI sessions (routes to status instead of raw print)."""
from __future__ import annotations

from rich.console import Console

from cli.ui_context import is_quiet_console, notify_progress

_fallback = Console()


def agent_note(message: str, *, also_print: bool = False) -> None:
    """Log agent activity — updates Live status when quiet mode is on."""
    plain = _strip_rich(message)
    if is_quiet_console():
        notify_progress(plain)
        return
    if also_print:
        _fallback.print(message)


def _strip_rich(text: str) -> str:
    return text.replace("[bold]", "").replace("[/bold]", "").replace("[cyan]", "").replace("[/cyan]", "").replace("[green]", "").replace("[/green]", "").replace("[dim]", "").replace("[/dim]", "").replace("\n", " ").strip()
