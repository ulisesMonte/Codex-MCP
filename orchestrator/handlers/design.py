"""Design handler."""
from __future__ import annotations

from typing import TYPE_CHECKING

from agents.design import mcp_design_agent_node
from events.types import EventTypes

if TYPE_CHECKING:
    from events.bus import EventBus
    from events.model import MCPEvent
    from orchestrator.session_state import SessionStateStore


class DesignHandler:
    name = "DesignHandler"

    def handles(self) -> set[str]:
        return {EventTypes.SCOUT_VALIDATION_COMPLETED}

    def handle(self, event: MCPEvent, store: SessionStateStore, bus: EventBus) -> None:
        session_id = event.session_id
        state = store.snapshot(session_id)
        if state.get("_design_done"):
            return
        updates = mcp_design_agent_node(state)
        store.update(session_id, {**updates, "_design_done": True})
