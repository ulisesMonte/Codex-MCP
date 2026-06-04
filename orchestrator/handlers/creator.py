"""Code generation handlers (initial + retry)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from agents.creator import mcp_creator_agent_node
from events.types import EventTypes

if TYPE_CHECKING:
    from events.bus import EventBus
    from events.model import MCPEvent
    from orchestrator.session_state import SessionStateStore


def _run_creator(session_id: str, store: SessionStateStore) -> None:
    state = store.snapshot(session_id)
    updates = mcp_creator_agent_node(state)
    store.update(session_id, updates)


class CreatorHandler:
    name = "CreatorHandler"

    def handles(self) -> set[str]:
        return {EventTypes.DESIGN_COMPLETED, EventTypes.VALIDATION_RETRY_SCHEDULED}

    def handle(self, event: MCPEvent, store: SessionStateStore, bus: EventBus) -> None:
        _run_creator(event.session_id, store)


class CreatorRetryHandler(CreatorHandler):
    """Alias kept for transition docs and backward compatibility."""

    name = "CreatorRetryHandler"

    def handles(self) -> set[str]:
        return {EventTypes.VALIDATION_RETRY_SCHEDULED}
