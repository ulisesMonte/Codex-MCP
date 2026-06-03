"""Explicit CLI: conversation + requirements vs event log."""
from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from cli.requirement_summary import format_requirement_snapshot
from agents.requirements_enrichment import user_facing_gaps
from models.checklist_labels import CHECKLIST_LABELS
from models.mcp_requirement import MCPRequirement
from orchestrator.state import MCPFactoryState
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

PHASE_LABELS: dict[str, str] = {
    "gathering": "Requirements gathering",
    "complete": "Requirements confirmed — generating MCP",
    "designing": "Technical design",
    "creating": "Code generation",
    "validating": "Validation",
    "deploying": "Deployment",
    "done": "Completed",
    "error": "Error",
}


def agent_prompt_text(state: MCPFactoryState) -> str:
    prompt = (state.get("agent_prompt") or "").strip()
    if prompt:
        return prompt
    return last_agent_message(state.get("messages", [])) or ""


def last_agent_message(messages: list[BaseMessage]) -> str | None:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            text = str(msg.content).strip()
            if text and not text.startswith("{"):
                return text
    return None


def show_session_intro(console: Console, session_id: str) -> None:
    console.print()
    console.print(
        Panel(
            "[bold]MCP requirements session[/bold]\n\n"
            "• [cyan]Chat[/cyan]: agent questions and your replies\n"
            "• [dim]Events[/dim]: technical log on the right\n\n"
            "When the summary looks right → type [bold cyan]confirm[/bold cyan]",
            title="[bold cyan]MCP Factory[/bold cyan]",
            border_style="cyan",
        )
    )
    console.print(f"[dim]Session: {session_id}[/dim]\n")


def show_conversation(console: Console, state: MCPFactoryState) -> None:
    """Full dialogue so the user sees what was said."""
    messages = state.get("messages", [])
    if not messages:
        return

    blocks: list = []
    for msg in messages[-8:]:
        if isinstance(msg, HumanMessage):
            blocks.append(
                Panel(
                    msg.content,
                    title="[bold green]You[/bold green]",
                    border_style="green",
                    padding=(0, 1),
                )
            )
        elif isinstance(msg, AIMessage) and msg.content:
            blocks.append(
                Panel(
                    Markdown(str(msg.content)),
                    title="[bold cyan]Agent (requirements)[/bold cyan]",
                    border_style="cyan",
                    padding=(0, 1),
                )
            )

    console.print()
    console.rule("[bold]Conversation[/bold]", style="white")
    console.print(Group(*blocks))


def show_user_input_prompt(console: Console, state: MCPFactoryState, *, turn: int) -> None:
    console.print()
    console.print(
        Panel(
            "[bold yellow]WAITING FOR YOUR REPLY[/bold yellow]\n"
            "Type below on the [bold]YOU[/bold] line.",
            border_style="yellow",
            padding=(0, 1),
        )
    )
    console.print(
        f"[dim]Phase:[/dim] {PHASE_LABELS.get(state.get('phase', 'gathering'), '—')}  ·  "
        f"[dim]Turno {turn}[/dim]\n"
    )

    if turn == 1 and not state.get("messages"):
        console.print(
            "[white]Example: BigQuery MCP, one tool, code only, "
            "google-cloud-bigquery dependency.[/white]\n"
        )
        return

    show_conversation(console, state)
    requirement: MCPRequirement | None = state.get("requirement")
    if requirement is not None:
        console.print()
        show_requirement_snapshot_panel(console, requirement)
        pending = pending_items(requirement)
        if pending:
            console.print(
                Panel(
                    "\n".join(f"• {p}" for p in pending),
                    title="[bold yellow]El agente necesita esto[/bold yellow]",
                    border_style="yellow",
                )
            )
    console.print()


def show_user_message_echo(console: Console, text: str) -> None:
    console.print(
        Panel(
            text,
            title="[bold green]You sent[/bold green]",
            border_style="green",
            padding=(0, 1),
        )
    )


def show_processing(console: Console, state: MCPFactoryState) -> None:
    phase = state.get("phase", "gathering")
    msg = (
        "Analyzing your message with Ollama…"
        if phase == "gathering"
        else "Generating MCP (design → code → validation)…"
    )
    console.print()
    console.rule("[bold blue]Processing[/bold blue]", style="blue")
    console.print(f"[cyan]{msg}[/cyan]  [dim](do not type yet)[/dim]\n")


def show_gathering_turn(console: Console, state: MCPFactoryState) -> None:
    """Main output after a requirements turn — conversation first, never raw JSON."""
    console.print()
    console.rule("[bold cyan]Agent response[/bold cyan]", style="cyan")

    prompt = agent_prompt_text(state)
    console.print(
        Panel(
            Markdown(prompt) if prompt else "[yellow]No agent message[/yellow]",
            title="[bold]Agent questions / summary[/bold]",
            border_style="cyan",
            padding=(1, 2),
        )
    )

    requirement: MCPRequirement | None = state.get("requirement")
    if requirement is not None:
        show_requirement_snapshot_panel(console, requirement)
        _show_checklist_table(console, requirement)
        pending = pending_items(requirement)
        if pending:
            console.print(
                Panel(
                    "\n".join(f"[yellow]→[/yellow] {p}" for p in pending),
                    title="[bold yellow]Still missing[/bold yellow]",
                    border_style="yellow",
                )
            )
        elif requirement.is_ready():
            console.print(
                "[bold green]✓ Checklist complete.[/bold green] "
                "If it matches what you want, type [bold cyan]confirm[/bold cyan].\n"
            )

    show_conversation(console, state)
    console.print(
        "[bold green]▶ Next:[/bold green] find "
        "[bold yellow]WAITING FOR YOUR REPLY[/bold yellow] and the [bold]YOU[/bold] line.\n"
    )


def show_requirement_snapshot_panel(console: Console, requirement: MCPRequirement) -> None:
    console.print(
        Panel(
            Markdown(format_requirement_snapshot(requirement)),
            title="[bold]Requirements collected (summary)[/bold]",
            border_style="dim cyan",
            padding=(1, 2),
        )
    )


def show_pipeline_finished(console: Console, state: MCPFactoryState) -> None:
    phase = state.get("phase", "done")
    if phase == "error":
        from orchestrator.graph import _resolve_pipeline_error
        error = _resolve_pipeline_error(state)
        console.print(
            Panel(
                f"[red]{error}[/red]\n\n"
                "Restart with: [cyan]python main.py create[/cyan]",
                title="[bold red]Error[/bold red]",
                border_style="red",
            )
        )
        return

    generated = state.get("generated_mcp")
    path = getattr(generated, "server_path", None) if generated else None
    body = "[bold green]MCP generated successfully.[/bold green]"
    if path:
        body += f"\n\nFile: [cyan]{path}[/cyan]"
    console.print(Panel(body, title="[bold green]Done[/bold green]", border_style="green"))


def show_events_sidebar(console: Console, table, *, max_rows: int = 6) -> None:
    """Compact technical log — after conversation blocks."""
    console.print()
    console.print(Rule("[dim]Events (technical log)[/dim]", style="dim"))
    # Shrink table: reuse view with fewer rows by slicing if needed
    console.print(table)


def pending_items(requirement: MCPRequirement) -> list[str]:
    return user_facing_gaps(requirement)


def _show_checklist_table(console: Console, requirement: MCPRequirement) -> None:
    table = Table(title="Checklist", border_style="dim", show_header=True)
    table.add_column("Item", style="white")
    table.add_column("Status", justify="center", width=8)
    for key, done in requirement.checklist().items():
        label = CHECKLIST_LABELS.get(key, key)
        table.add_row(label, "[green]OK[/green]" if done else "[yellow]MISSING[/yellow]")
    console.print(table)


# Backward-compatible alias
def show_agent_turn_result(console: Console, state: MCPFactoryState) -> None:
    show_gathering_turn(console, state)
