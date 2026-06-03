"""
MCP Factory - CLI entry point.

Commands:
  create       Start a new MCP creation session
  list         Show registered MCPs
  status       Show status of a registered MCP
  stop         Stop a running MCP server
  show         Print generated code
  events       Show the event log for a session
  list-events  List event log sessions
"""
from __future__ import annotations

from pathlib import Path
import sys

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from cli.processes import attach_registered_process
from cli.session_runner import MCPCreateSessionRunner
from deployer.process_manager import ProcessManager
from events import JsonlEventStore
from events.view import events_to_table
from llm.ollama_client import check_ollama_running, get_available_ollama_models
from orchestrator.graph import build_graph
from registry.registry_manager import RegistryManager

app = typer.Typer(
    name="mcp-factory",
    help="MCP Factory - generate MCP servers from natural language",
    rich_markup_mode="rich",
    add_completion=False,
)
console = Console()


def _print_banner() -> None:
    console.print()
    console.print(
        Panel(
            "[bold cyan]MCP Factory[/bold cyan]\n"
            "[dim]Multi-agent system for dynamic MCP server generation[/dim]\n"
            "[dim]Powered by local LLMs via Ollama[/dim]",
            border_style="cyan",
            padding=(1, 4),
        )
    )
    console.print()


def _check_ollama() -> bool:
    if not check_ollama_running():
        console.print(
            Panel(
                "[red]Ollama is not running.[/red]\n\n"
                "Start it with:\n"
                "  [cyan]ollama serve[/cyan]\n\n"
                "Then pull a model:\n"
                "  [cyan]ollama pull llama3.1:8b[/cyan]\n"
                "  [cyan]ollama pull qwen2.5-coder:7b[/cyan]",
                title="[bold red]Ollama Required[/bold red]",
                border_style="red",
            )
        )
        return False

    models = get_available_ollama_models()
    if not models:
        console.print(
            Panel(
                "[yellow]Ollama is running but no models are pulled.[/yellow]\n\n"
                "Pull a model to get started:\n"
                "  [cyan]ollama pull llama3.1:8b[/cyan]\n"
                "  [cyan]ollama pull qwen2.5-coder:7b[/cyan]",
                title="[bold yellow]No Models Found[/bold yellow]",
                border_style="yellow",
            )
        )
        return False

    suffix = "..." if len(models) > 5 else ""
    console.print(f"[dim]Available models: {', '.join(models[:5])}{suffix}[/dim]")
    return True


@app.command()
def create() -> None:
    """Start a new MCP creation session."""
    _print_banner()
    MCPCreateSessionRunner(
        console=console,
        graph_factory=build_graph,
        check_ollama=_check_ollama,
    ).run()


@app.command()
def list() -> None:
    """List all registered MCP servers."""
    registry = RegistryManager()
    mcps = registry.get_all()

    if not mcps:
        console.print("[dim]No MCPs registered yet. Run 'python main.py create' to get started.[/dim]")
        return

    table = Table(title="Registered MCP Servers", border_style="cyan")
    table.add_column("Name", style="bold cyan")
    table.add_column("Description", style="white", max_width=40)
    table.add_column("Transport", style="yellow")
    table.add_column("Mode", style="magenta")
    table.add_column("Tools", style="green")
    table.add_column("Status", style="bold")
    table.add_column("Created", style="dim")

    for mcp in mcps:
        status_style = "green" if mcp.get("status") == "deployed" else "white"
        table.add_row(
            mcp.get("name", ""),
            mcp.get("description", "")[:40],
            mcp.get("transport", "stdio"),
            mcp.get("output_mode", "code_only"),
            ", ".join(mcp.get("tools", [])) or "-",
            f"[{status_style}]{mcp.get('status', 'generated')}[/{status_style}]",
            mcp.get("created_at", "")[:10],
        )

    console.print()
    console.print(table)
    console.print()


@app.command()
def status(name: str = typer.Argument(..., help="MCP server name")) -> None:
    """Show status of a registered MCP server."""
    registry = RegistryManager()
    entry = registry.get_by_name(name)

    if not entry:
        console.print(f"[red]No MCP named '{name}' found in registry.[/red]")
        raise typer.Exit(1)

    proc = attach_registered_process(entry)
    if entry.get("status") == "deployed" and not proc:
        registry.update_status(name, "stopped", deployment_pid=None)
        entry["status"] = "stopped"
        entry["deployment_pid"] = None

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Field", style="bold cyan", width=18)
    table.add_column("Value")

    table.add_row("Name", entry.get("name", ""))
    table.add_row("Description", entry.get("description", ""))
    table.add_row("Transport", entry.get("transport", "stdio"))
    table.add_row("Output mode", entry.get("output_mode", "code_only"))
    table.add_row("Tools", ", ".join(entry.get("tools", [])) or "-")
    table.add_row("Dependencies", ", ".join(entry.get("dependencies", [])) or "none")
    table.add_row("File", entry.get("server_path", ""))
    table.add_row("Registry status", entry.get("status", ""))
    table.add_row("Created", entry.get("created_at", "")[:19])

    if proc:
        alive = "[green]running[/green]" if proc.is_alive() else "[red]stopped[/red]"
        table.add_row("Process", f"{alive} (PID {proc.pid})")
        if proc.url:
            table.add_row("URL", proc.url)

    console.print()
    console.print(Panel(table, title=f"[bold cyan]MCP: {name}[/bold cyan]", border_style="cyan"))
    console.print()


@app.command()
def stop(name: str = typer.Argument(..., help="MCP server name to stop")) -> None:
    """Stop a running MCP server."""
    registry = RegistryManager()
    entry = registry.get_by_name(name)
    if not entry:
        console.print(f"[red]No MCP named '{name}' found in registry.[/red]")
        raise typer.Exit(1)

    attach_registered_process(entry)
    pm = ProcessManager.get()
    if pm.stop(name):
        console.print(f"[green]Stopped: {name}[/green]")
        registry.update_status(name, "stopped", deployment_pid=None, deployment_url=None)
    else:
        console.print(f"[yellow]No running process found for '{name}'.[/yellow]")


@app.command()
def show(name: str = typer.Argument(..., help="MCP server name")) -> None:
    """Print the generated source code of an MCP."""
    registry = RegistryManager()
    entry = registry.get_by_name(name)

    if not entry:
        console.print(f"[red]No MCP named '{name}' found in registry.[/red]")
        raise typer.Exit(1)

    server_path = Path(entry.get("server_path", ""))
    if not server_path.exists():
        console.print(f"[red]File not found: {server_path}[/red]")
        raise typer.Exit(1)

    code = server_path.read_text(encoding="utf-8")
    console.print()
    console.print(f"[dim]-- {server_path} --[/dim]")
    console.print(Syntax(code, "python", theme="monokai", line_numbers=True))
    console.print()


@app.command("events")
def show_events(session_id: str = typer.Argument(..., help="Event session ID")) -> None:
    """Show the event log for a session."""
    store = JsonlEventStore()
    session_events = store.read_session(session_id)
    if not session_events:
        console.print(f"[yellow]No events found for session '{session_id}'.[/yellow]")
        raise typer.Exit(1)
    console.print()
    console.print(events_to_table(session_events, title=f"Events: {session_id}"))
    console.print()


@app.command("list-events")
def list_events() -> None:
    """List event log sessions."""
    sessions = JsonlEventStore().list_sessions()
    if not sessions:
        console.print("[dim]No event sessions found yet.[/dim]")
        return

    table = Table(title="Event Sessions", border_style="cyan")
    table.add_column("Session ID", style="bold cyan")
    for session_id in sessions:
        table.add_row(session_id)
    console.print()
    console.print(table)
    console.print()


if __name__ == "__main__":
    app()
