"""Chat-first terminal UI with compact events panel (top-right)."""
from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from rich.console import Console, Group, RenderableType
from rich.layout import Layout
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agents.requirements_enrichment import user_facing_gaps
from cli.interaction_ui import agent_prompt_text
from cli.requirement_summary import format_requirement_snapshot
from events.view import EventLogView
from models.mcp_requirement import MCPRequirement
from orchestrator.state import MCPFactoryState


@dataclass
class ChatLine:
    role: str  # user | agent | system | status
    body: str


@dataclass
class GatheringChatUI:
    """Interactive chat (main) + event log (secondary, right column)."""

    console: Console
    event_view: EventLogView
    lines: list[ChatLine] = field(default_factory=list)
    status: str = "Ready for your first message."
    thinking: str = ""
    _last_summary: str = ""

    def set_thinking(self, text: str) -> None:
        self.thinking = text.strip()

    def append_thinking(self, text: str, *, max_lines: int = 10) -> None:
        """Rolling log of pipeline steps (design, scouts, codegen…)."""
        line = text.strip()
        if not line:
            return
        prev = self.thinking.splitlines() if self.thinking else []
        prev.append(line)
        self.thinking = "\n".join(prev[-max_lines:])

    def clear_thinking(self) -> None:
        self.thinking = ""

    def add_user(self, text: str) -> None:
        self.lines.append(ChatLine("user", text))

    def add_agent(self, text: str) -> None:
        text = text.strip()
        if any(ln.role == "agent" and ln.body == text for ln in self.lines[-4:]):
            return
        self.lines.append(ChatLine("agent", text))

    def add_system(self, text: str) -> None:
        if text.strip():
            self.lines.append(ChatLine("system", text.strip()))

    def set_status(self, text: str) -> None:
        self.status = text

    def _strip_state_system_lines(self) -> None:
        """Remove prior summary/hint blocks so each turn shows fresh state."""
        markers = ("**Current summary**", "**For you (if applicable):**", "Checklist complete.")
        self.lines = [
            ln
            for ln in self.lines
            if ln.role != "system" or not any(ln.body.startswith(m) for m in markers)
        ]

    def apply_state_after_turn(self, state: MCPFactoryState) -> None:
        """Push agent reply + requirement snapshot into the chat."""
        prompt = agent_prompt_text(state)
        if prompt:
            self.add_agent(prompt)

        requirement: MCPRequirement | None = state.get("requirement")
        if requirement is not None:
            snapshot = format_requirement_snapshot(requirement)
            if requirement.mcp_name or requirement.description or requirement.tools:
                self._strip_state_system_lines()
                self._last_summary = snapshot
                self.add_system(f"**Current summary**\n\n{snapshot}")
            elif self._last_summary:
                self._strip_state_system_lines()
                self.add_system(
                    f"**Current summary** _(updating…)_\n\n{self._last_summary}"
                )

            missing = user_facing_gaps(requirement)
            if missing:
                bullets = "\n".join(f"- {m}" for m in missing)
                self.add_system(f"**For you (if applicable):**\n\n{bullets}")
            elif requirement.is_ready():
                self.add_system(
                    "Checklist complete. If the summary looks right, type **confirm**."
                )

        self.set_status("Your turn — type your reply below.")

    def sync_from_messages(self, messages: list[BaseMessage]) -> None:
        """Rebuild chat lines from LangChain history (dedupe)."""
        self.lines.clear()
        for msg in messages:
            if isinstance(msg, HumanMessage) and msg.content:
                self.add_user(str(msg.content))
            elif isinstance(msg, AIMessage) and msg.content:
                text = str(msg.content).strip()
                if text and not text.startswith("{"):
                    self.add_agent(text)

    def build(self) -> Layout:
        layout = Layout(name="root")
        layout.split_row(
            Layout(self._render_chat_panel(), name="chat", ratio=7),
            Layout(self._render_events_panel(), name="events", ratio=3),
        )
        return layout

    def print_screen(self, *, clear: bool = False) -> None:
        """Static full-screen chat + events (no Live)."""
        if clear:
            self.console.clear()
        self.console.print(self.build())

    def _render_chat_panel(self) -> Panel:
        blocks: list[RenderableType] = []

        if not self.lines:
            blocks.append(
                Text(
                    "Describe the MCP you want to create.\n"
                    "Example: BigQuery tool, code only, etc.",
                    style="dim",
                )
            )
        else:
            for line in self.lines[-12:]:
                blocks.append(self._line_panel(line))

        blocks.append(Panel(
            Text(self.status, style="bold cyan"),
            title="Status",
            border_style="blue",
            padding=(0, 1),
        ))
        if self.thinking:
            blocks.append(Panel(
                Text(self.thinking, style="dim italic"),
                title="[dim]Thinking[/dim]",
                border_style="dim",
                padding=(0, 1),
            ))
        blocks.append(Text(
            "Type below on the YOU line — exit / quit to leave",
            style="bold yellow",
        ))

        return Panel(
            Group(*blocks),
            title="[bold cyan]Chat — Requirements[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
        )

    def _line_panel(self, line: ChatLine) -> Panel:
        if line.role == "user":
            return Panel(
                line.body,
                title="[bold green]You[/bold green]",
                border_style="green",
                padding=(0, 1),
            )
        if line.role == "agent":
            return Panel(
                Markdown(line.body),
                title="[bold cyan]Agent[/bold cyan]",
                border_style="cyan",
                padding=(0, 1),
            )
        return Panel(
            Markdown(line.body),
            title="[bold yellow]System[/bold yellow]",
            border_style="yellow",
            padding=(0, 1),
        )

    def _render_events_panel(self) -> Panel:
        table = self._compact_events_table()
        return Panel(
            table,
            title="[dim]Events[/dim]",
            border_style="dim",
            padding=(0, 0),
        )

    def _compact_events_table(self) -> Table:
        table = Table(
            show_header=True,
            header_style="dim",
            border_style="dim",
            pad_edge=False,
            expand=True,
        )
        table.add_column("#", justify="right", style="dim", width=3)
        table.add_column("Event", style="cyan", no_wrap=True)
        table.add_column("Msg", style="dim", overflow="fold")

        for event in self.event_view.events[-12:]:
            short_type = event.type.replace("MCP", "").replace("Requested", "")
            if len(short_type) > 22:
                short_type = short_type[:19] + "…"
            table.add_row(
                str(event.sequence),
                short_type,
                event.message[:50],
            )
        if not self.event_view.events:
            table.add_row("—", "—", "no events")
        return table
