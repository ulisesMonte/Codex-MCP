"""Runtime registry for session-scoped event buses."""
from __future__ import annotations

from events.bus import EventBus
from events.store import JsonlEventStore
from orchestrator.settings import use_event_orchestration

_BUSES: dict[str, EventBus] = {}


def get_event_bus(session_id: str, store: JsonlEventStore | None = None) -> EventBus:
    if session_id not in _BUSES:
        bus = EventBus(session_id=session_id, store=store)
        if use_event_orchestration():
            from orchestrator.coordinator import get_coordinator

            get_coordinator(session_id, bus)
        _BUSES[session_id] = bus
    return _BUSES[session_id]


def reset_event_bus(session_id: str) -> None:
    if use_event_orchestration():
        from orchestrator.coordinator import reset_coordinator

        reset_coordinator(session_id)
    _BUSES.pop(session_id, None)
