"""Rich render helpers for MCP Factory event logs."""
from __future__ import annotations

from datetime import datetime

from rich.table import Table

from events.model import MCPEvent


class EventLogView:
    """Keeps a compact in-memory view of session events for Rich Live."""

    def __init__(self, max_rows: int = 14):
        self.max_rows = max_rows
        self.events: list[MCPEvent] = []

    def on_event(self, event: MCPEvent) -> None:
        self.events.append(event)

    def render(self) -> Table:
        table = Table(title="MCP Factory Events", border_style="cyan")
        table.add_column("#", justify="right", style="dim", width=4)
        table.add_column("Time", style="dim", width=8)
        table.add_column("Level", width=8)
        table.add_column("Event", style="bold cyan", width=26)
        table.add_column("Message", style="white")

        for event in self.events[-self.max_rows:]:
            table.add_row(
                str(event.sequence),
                _short_time(event.timestamp),
                _style_level(event.level),
                event.type,
                event.message,
            )
        return table


def events_to_table(events: list[MCPEvent], title: str = "MCP Factory Events") -> Table:
    view = EventLogView(max_rows=max(len(events), 1))
    for event in events:
        view.on_event(event)
    table = view.render()
    table.title = title
    return table


def _short_time(timestamp: str) -> str:
    try:
        return datetime.fromisoformat(timestamp).strftime("%H:%M:%S")
    except ValueError:
        return timestamp[:8]


def _style_level(level: str) -> str:
    if level == "error":
        return "[red]error[/red]"
    if level == "warning":
        return "[yellow]warning[/yellow]"
    if level == "debug":
        return "[dim]debug[/dim]"
    return "[green]info[/green]"
