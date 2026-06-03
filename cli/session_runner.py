"""Interactive MCP creation session runner."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

import typer
from langchain_core.messages import HumanMessage
from rich.console import Console

from cli.chat_session import GatheringChatUI
from cli.interaction_ui import show_pipeline_finished
from cli.pipeline_status import status_for_event
from cli.pipeline_ui import ThrottledRefresher, will_run_full_pipeline
from cli.ui_context import reset_ui_callbacks, set_ui_callbacks
from events import EventTypes, get_event_bus, reset_event_bus
from events.bus import EventBus
from events.view import EventLogView
from orchestrator.coordinator import get_coordinator, reset_coordinator
from orchestrator.settings import use_event_orchestration
from orchestrator.state import MCPFactoryState

GraphFactory = Callable[[], object]
OllamaCheck = Callable[[], bool]

# Only redraw the events column on these during LLM wait (not every RequirementUpdated)
_GATHERING_MILESTONE_EVENTS = frozenset({
    EventTypes.REQUIREMENTS_STARTED,
    EventTypes.REQUIREMENTS_COMPLETED,
    EventTypes.CLARIFICATION_NEEDED,
    EventTypes.REQUIREMENT_UPDATED,
})


class MCPCreateSessionRunner:
    """Chat-first create session; events stay in the right column."""

    def __init__(
        self,
        console: Console,
        graph_factory: GraphFactory,
        check_ollama: OllamaCheck,
        bus_factory: Callable[[str], EventBus] = get_event_bus,
    ):
        self.console = console
        self.graph_factory = graph_factory
        self.check_ollama = check_ollama
        self.bus_factory = bus_factory

    def run(self) -> None:
        session_id = new_session_id()
        reset_event_bus(session_id)
        bus = self.bus_factory(session_id)
        event_view = EventLogView(max_rows=12)
        chat = GatheringChatUI(console=self.console, event_view=event_view)
        pipeline_active: dict[str, bool] = {"on": False}
        waiting_llm: dict[str, bool] = {"on": False}
        refresher = ThrottledRefresher(min_interval_s=2.5)

        def refresh_ui(*, clear: bool = False, force: bool = False) -> None:
            """Static full-screen redraw — no Rich Live (stable on Windows)."""
            if force or refresher.should_refresh():
                chat.print_screen(clear=clear)
                refresher.mark_refreshed()

        def on_event(event) -> None:
            event_view.on_event(event)
            status = status_for_event(event)
            if not status:
                return

            if pipeline_active["on"]:
                chat.set_status(status)
                chat.append_thinking(status)
                refresh_ui(clear=True, force=True)
                return

            if waiting_llm["on"]:
                chat.set_status(status)
                if event.type in _GATHERING_MILESTONE_EVENTS:
                    chat.append_thinking(status)
                    refresh_ui(clear=False, force=True)
                return

            chat.set_status(status)
            refresh_ui(clear=False)

        def on_progress(msg: str) -> None:
            chat.set_status(msg)
            if pipeline_active["on"]:
                chat.append_thinking(msg)
                refresh_ui(clear=True, force=True)
            elif waiting_llm["on"]:
                # Status line only — throttle full redraws during long Ollama calls
                refresh_ui(clear=False)

        def on_thinking(msg: str) -> None:
            if pipeline_active["on"]:
                chat.append_thinking(msg)
                refresh_ui(clear=True, force=True)

        bus.subscribe(on_event)
        bus.publish(
            EventTypes.CREATE_MCP_REQUESTED,
            "cli",
            "MCP creation session started",
            payload={"session_id": session_id},
        )

        if not self.check_ollama():
            bus.publish(
                EventTypes.SESSION_FAILED,
                "cli",
                "Session failed because Ollama is not ready",
                level="error",
                payload={"session_id": session_id},
            )
            raise typer.Exit(1)

        self.console.print()
        self.console.print(
            "[bold cyan]MCP Factory[/bold cyan] — "
            "[dim]chat on the left · events on the right[/dim]"
        )
        mode_label = "events" if use_event_orchestration() else "langgraph"
        self.console.print(f"[dim]Session: {session_id} · orchestration: {mode_label}[/dim]\n")

        graph = self.graph_factory()
        config = {"configurable": {"thread_id": session_id}}
        state = self._initial_state(session_id)

        while True:
            chat.print_screen()
            refresher.mark_refreshed()
            user_input = self._read_user_input(bus, state)
            if user_input is None:
                break
            if not user_input:
                chat.add_system("Empty message. Type your reply or `exit`.")
                continue

            chat.add_user(user_input)
            self._record_user_message(bus, state, user_input)
            pipeline_turn = will_run_full_pipeline(state, user_input)
            pipeline_active["on"] = pipeline_turn
            waiting_llm["on"] = not pipeline_turn

            if pipeline_turn:
                chat.clear_thinking()
                chat.set_status(
                    "Pipeline: scouts (4) → validator → design → codegen… "
                    "(varios minutos — seguí Events →)"
                )
                chat.append_thinking("Confirm recibido — iniciando pipeline industrial…")
            else:
                chat.clear_thinking()
                chat.set_status("Analizando tu mensaje (Ollama — puede tardar ~1–2 min)…")
                chat.append_thinking("Esperando respuesta del modelo…")

            ui_tokens = ()
            try:
                ui_tokens = set_ui_callbacks(
                    progress=on_progress,
                    thinking=on_thinking,
                    quiet_console=True,
                )
                refresher.reset()
                chat.print_screen(clear=True)
                refresher.mark_refreshed()

                if use_event_orchestration():
                    coordinator = get_coordinator(session_id, bus)
                    result = coordinator.run_user_turn(state)
                else:
                    result = graph.invoke(state, config=config)

                reset_ui_callbacks(*ui_tokens)
                chat.clear_thinking()
                pipeline_active["on"] = False
                waiting_llm["on"] = False

                state = result
                state["session_id"] = session_id
                if state.get("error") and state.get("phase") not in ("done", "gathering"):
                    state["phase"] = "error"
                phase = state.get("phase", "gathering")

                if phase == "gathering":
                    chat.apply_state_after_turn(state)
                    chat.print_screen(clear=True)
                    refresher.mark_refreshed()
                    continue

                if phase == "done":
                    bus.publish(
                        EventTypes.SESSION_COMPLETED,
                        "cli",
                        "MCP creation session completed",
                        payload={"phase": phase},
                    )
                    chat.set_status("Session completed.")
                    chat.print_screen()
                    show_pipeline_finished(self.console, state)
                    break

                if phase == "error":
                    from orchestrator.graph import _resolve_pipeline_error
                    err_detail = _resolve_pipeline_error(state)
                    self._publish_failure(
                        bus,
                        "MCP creation session failed",
                        {"phase": phase, "error": err_detail},
                    )
                    chat.set_status(f"Error: {err_detail[:120]}")
                    chat.add_system(f"**Error:**\n\n{err_detail}")
                    chat.print_screen()
                    show_pipeline_finished(self.console, state)
                    break

            except Exception as e:
                pipeline_active["on"] = False
                waiting_llm["on"] = False
                if ui_tokens:
                    reset_ui_callbacks(*ui_tokens)
                chat.clear_thinking()
                self._publish_failure(bus, "Pipeline error", {"error": str(e)})
                chat.set_status(f"Error: {e}")
                chat.print_screen()
                self.console.print(f"[red]Error: {e}[/red]")
                break

        self.console.print()

    def _initial_state(self, session_id: str) -> MCPFactoryState:
        return {
            "session_id": session_id,
            "messages": [],
            "requirement": None,
            "design": None,
            "generated_mcp": None,
            "phase": "gathering",
            "validation_attempts": 0,
            "error": None,
            "agent_prompt": None,
        }

    def _read_user_input(self, bus: EventBus, state: MCPFactoryState) -> str | None:
        self.console.print()
        try:
            user_input = self.console.input(
                "[bold black on yellow] YOU [/bold black on yellow] "
            ).strip()
        except (KeyboardInterrupt, EOFError):
            self.console.print("\n[dim]Session ended.[/dim]")
            self._publish_user_end(bus, state)
            return None

        if user_input.lower() in ("exit", "quit", "q"):
            self.console.print("[dim]Session ended.[/dim]")
            self._publish_user_end(bus, state)
            return None

        return user_input

    def _record_user_message(
        self,
        bus: EventBus,
        state: MCPFactoryState,
        user_input: str,
    ) -> None:
        if not use_event_orchestration():
            bus.publish(
                EventTypes.USER_MESSAGE_RECEIVED,
                "cli",
                "User message received",
                payload={"length": len(user_input)},
                dispatch=False,
            )
        state["messages"] = list(state.get("messages", [])) + [
            HumanMessage(content=user_input)
        ]

    def _publish_user_end(self, bus: EventBus, state: MCPFactoryState) -> None:
        bus.publish(
            EventTypes.SESSION_COMPLETED,
            "cli",
            "Session ended by user",
            payload={"phase": state.get("phase", "gathering")},
        )

    def _publish_failure(self, bus: EventBus, message: str, payload: dict) -> None:
        bus.publish(
            EventTypes.SESSION_FAILED,
            "cli",
            message,
            level="error",
            payload=payload,
        )


def new_session_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"mcp-factory-{stamp}-{uuid4().hex[:8]}"
