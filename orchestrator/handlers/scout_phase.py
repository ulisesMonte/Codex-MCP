"""Parallel scout phase + validation handler."""
from __future__ import annotations

from typing import TYPE_CHECKING

from agents.scout_api_agent import scout_api_agent_node
from agents.scout_data_agent import scout_data_agent_node
from agents.scout_docs_agent import scout_docs_agent_node
from agents.scout_mcp_agent import scout_mcp_agent_node
from agents.scout_validator_agent import scout_validator_agent_node
from events.types import EventTypes

if TYPE_CHECKING:
    from events.bus import EventBus
    from events.model import MCPEvent
    from orchestrator.session_state import SessionStateStore


class ScoutPhaseHandler:
    name = "ScoutPhaseHandler"

    def handles(self) -> set[str]:
        return {EventTypes.REQUIREMENTS_COMPLETED}

    def handle(self, event: MCPEvent, store: SessionStateStore, bus: EventBus) -> None:
        session_id = event.session_id
        state = store.snapshot(session_id)
        if state.get("phase") != "complete":
            return
        if state.get("_scout_phase_done"):
            return

        scout_nodes = (
            scout_mcp_agent_node,
            scout_api_agent_node,
            scout_data_agent_node,
            scout_docs_agent_node,
        )
        for node in scout_nodes:
            result = node(state)
            state = store.update(session_id, result)

        validator_result = scout_validator_agent_node(store.snapshot(session_id))
        store.update(session_id, {**validator_result, "_scout_phase_done": True})
