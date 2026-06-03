"""In-memory event bus with JSONL persistence."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from events.model import EventLevel, MCPEvent
from events.protocols import EventStore, EventSubscriber
from events.serialization import sanitize_payload
from events.store import JsonlEventStore

if TYPE_CHECKING:
    from events.dispatcher import EventDispatcher
    from orchestrator.session_state import SessionStateStore


class EventBus:
    """Publishes events, persists them, notifies subscribers, and optionally dispatches handlers."""

    def __init__(self, session_id: str, store: EventStore | None = None):
        self.session_id = session_id
        self.store = store or JsonlEventStore()
        self._subscribers: list[EventSubscriber] = []
        self._next_sequence = self.store.next_sequence(session_id)
        self._dispatcher: EventDispatcher | None = None
        self._state_store: SessionStateStore | None = None
        self._dispatch_enabled = False

    def attach_dispatcher(
        self,
        dispatcher: EventDispatcher,
        state_store: SessionStateStore,
    ) -> None:
        """Wire lifecycle handlers — used when ORCHESTRATION_MODE=events."""
        self._dispatcher = dispatcher
        self._state_store = state_store
        self._dispatch_enabled = True

    def publish(
        self,
        type: str,
        source: str,
        message: str,
        level: EventLevel = "info",
        payload: dict[str, Any] | None = None,
        *,
        dispatch: bool | None = None,
    ) -> MCPEvent:
        event = MCPEvent(
            session_id=self.session_id,
            sequence=self._next_sequence,
            type=type,
            source=source,
            level=level,
            message=message,
            payload=sanitize_payload(payload or {}),
        )
        self._next_sequence += 1
        self.store.append(event)
        for subscriber in list(self._subscribers):
            subscriber(event)
        should_dispatch = self._dispatch_enabled if dispatch is None else dispatch
        if should_dispatch and self._dispatcher is not None and self._state_store is not None:
            self._dispatcher.enqueue(event, store=self._state_store, bus=self)
        return event

    def subscribe(self, callback: EventSubscriber) -> None:
        self._subscribers.append(callback)
