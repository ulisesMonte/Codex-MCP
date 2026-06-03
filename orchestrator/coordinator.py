"""Pipeline coordinator — event-driven lifecycle orchestration."""
from __future__ import annotations

from typing import TYPE_CHECKING

from events.dispatcher import EventDispatcher
from events.types import EventTypes
from orchestrator.handlers import register_pipeline_handlers
from orchestrator.session_state import SessionStateStore, get_session_state_store
from orchestrator.settings import orchestration_mode, use_event_orchestration
from orchestrator.state import MCPFactoryState

if TYPE_CHECKING:
    from events.bus import EventBus

_COORDINATORS: dict[str, PipelineCoordinator] = {}


class PipelineCoordinator:
    """
    Session-scoped coordinator: fixed transition table + event handlers.

    The LLM produces artifacts (requirement, design, code); handlers validate
    state and publish domain events that mark lifecycle phases.
    """

    def __init__(
        self,
        session_id: str,
        bus: EventBus,
        store: SessionStateStore | None = None,
    ) -> None:
        self.session_id = session_id
        self.bus = bus
        self.store = store or get_session_state_store()
        self.dispatcher = EventDispatcher()
        register_pipeline_handlers(self.dispatcher)
        self.bus.attach_dispatcher(self.dispatcher, self.store)

    def init_state(self, state: MCPFactoryState) -> MCPFactoryState:
        return self.store.init(self.session_id, state)

    def run_user_turn(self, state: MCPFactoryState) -> MCPFactoryState:
        """Process one user message through the event-driven pipeline."""
        self.store.init(self.session_id, state)
        self.bus.publish(
            EventTypes.USER_MESSAGE_RECEIVED,
            "coordinator",
            "User turn — dispatching to requirements handler",
            payload={"session_id": self.session_id},
        )
        return self.store.snapshot(self.session_id)

    def snapshot(self) -> MCPFactoryState:
        return self.store.snapshot(self.session_id)


def get_coordinator(session_id: str, bus: EventBus) -> PipelineCoordinator:
    if session_id not in _COORDINATORS:
        _COORDINATORS[session_id] = PipelineCoordinator(session_id, bus)
    return _COORDINATORS[session_id]


def reset_coordinator(session_id: str) -> None:
    coord = _COORDINATORS.pop(session_id, None)
    if coord is not None:
        coord.dispatcher.reset()
