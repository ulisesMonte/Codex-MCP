"""Registry update handlers."""
from __future__ import annotations

from typing import TYPE_CHECKING

from events.types import EventTypes
from registry.registry_manager import registry_updater_node

if TYPE_CHECKING:
    from events.bus import EventBus
    from events.model import MCPEvent
    from orchestrator.session_state import SessionStateStore


class RegistryHandler:
    name = "RegistryHandler"

    def handles(self) -> set[str]:
        return {EventTypes.CODE_READY}

    def handle(self, event: MCPEvent, store: SessionStateStore, bus: EventBus) -> None:
        session_id = event.session_id
        state = store.snapshot(session_id)
        if state.get("_registry_done"):
            return
        updates = registry_updater_node(state)
        store.update(session_id, {**updates, "_registry_done": True})


class RegistryDeployHandler:
    name = "RegistryDeployHandler"

    def handles(self) -> set[str]:
        return {EventTypes.MCP_DEPLOYED}

    def handle(self, event: MCPEvent, store: SessionStateStore, bus: EventBus) -> None:
        session_id = event.session_id
        state = store.snapshot(session_id)
        if state.get("_registry_done"):
            return
        updates = registry_updater_node(state)
        store.update(session_id, {**updates, "_registry_done": True})
