"""Deploy handler."""
from __future__ import annotations

from typing import TYPE_CHECKING

from deployer.local_deployer import deployer_node
from events.types import EventTypes

if TYPE_CHECKING:
    from events.bus import EventBus
    from events.model import MCPEvent
    from orchestrator.session_state import SessionStateStore


class DeployHandler:
    name = "DeployHandler"

    def handles(self) -> set[str]:
        return {EventTypes.VALIDATION_PASSED}

    def handle(self, event: MCPEvent, store: SessionStateStore, bus: EventBus) -> None:
        session_id = event.session_id
        state = store.snapshot(session_id)
        if state.get("_deploy_done"):
            return
        updates = deployer_node(state)
        store.update(session_id, {**updates, "_deploy_done": True})
