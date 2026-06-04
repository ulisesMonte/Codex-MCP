"""Validation handler."""
from __future__ import annotations

from typing import TYPE_CHECKING

from agents.validator import validator_agent_node
from events.types import EventTypes

if TYPE_CHECKING:
    from events.bus import EventBus
    from events.model import MCPEvent
    from orchestrator.session_state import SessionStateStore


class ValidatorHandler:
    name = "ValidatorHandler"

    def handles(self) -> set[str]:
        return {EventTypes.CODE_GENERATED}

    def handle(self, event: MCPEvent, store: SessionStateStore, bus: EventBus) -> None:
        session_id = event.session_id
        state = store.snapshot(session_id)
        updates = validator_agent_node(state)
        store.update(session_id, updates)
