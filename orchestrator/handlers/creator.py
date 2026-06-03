"""Code generation handlers (initial + retry)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from agents.mcp_creator_agent import mcp_creator_agent_node
from events.types import EventTypes

if TYPE_CHECKING:
    from events.bus import EventBus
    from events.model import MCPEvent
    from orchestrator.session_state import SessionStateStore


class CreatorHandler:
    name = "CreatorHandler"

    def handles(self) -> set[str]:
        return {EventTypes.DESIGN_COMPLETED}

    def handle(self, event: MCPEvent, store: SessionStateStore, bus: EventBus) -> None:
        session_id = event.session_id
        state = store.snapshot(session_id)
        updates = mcp_creator_agent_node(state)
        store.update(session_id, updates)


class CreatorRetryHandler:
    name = "CreatorRetryHandler"

    def handles(self) -> set[str]:
        return {EventTypes.VALIDATION_RETRY_SCHEDULED}

    def handle(self, event: MCPEvent, store: SessionStateStore, bus: EventBus) -> None:
        session_id = event.session_id
        state = store.snapshot(session_id)
        updates = mcp_creator_agent_node(state)
        store.update(session_id, updates)
