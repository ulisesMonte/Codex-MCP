"""Parallel scout phase + validation handler."""
from __future__ import annotations

from typing import TYPE_CHECKING

from agents.scouts.api import scout_api_agent_node
from agents.scouts.data import scout_data_agent_node
from agents.scouts.docs import scout_docs_agent_node
from agents.scouts.mcp import scout_mcp_agent_node
from agents.scouts.validator import scout_validator_agent_node
from events.types import EventTypes
from orchestrator.scout_runner import run_scouts_parallel

if TYPE_CHECKING:
    from events.bus import EventBus
    from events.model import MCPEvent
    from orchestrator.session_state import SessionStateStore

_SCOUT_NODES = (
    scout_mcp_agent_node,
    scout_api_agent_node,
    scout_data_agent_node,
    scout_docs_agent_node,
)


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

        scout_updates = run_scouts_parallel(state, _SCOUT_NODES)
        store.update(session_id, scout_updates)

        validator_result = scout_validator_agent_node(store.snapshot(session_id))
        store.update(session_id, {**validator_result, "_scout_phase_done": True})
