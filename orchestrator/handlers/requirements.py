"""Requirements gathering handler."""
from __future__ import annotations

from typing import TYPE_CHECKING

from agents.requirements_agent import requirements_agent_node
from events.types import EventTypes

if TYPE_CHECKING:
    from events.bus import EventBus
    from events.model import MCPEvent
    from orchestrator.session_state import SessionStateStore


class RequirementsHandler:
    name = "RequirementsHandler"

    def handles(self) -> set[str]:
        return {EventTypes.USER_MESSAGE_RECEIVED}

    def handle(self, event: MCPEvent, store: SessionStateStore, bus: EventBus) -> None:
        session_id = event.session_id
        state = store.snapshot(session_id)
        updates = requirements_agent_node(state)
        store.update(session_id, updates)
