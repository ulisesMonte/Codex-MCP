"""Event dispatcher — routes domain events to registered lifecycle handlers."""
from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Protocol

from events.model import MCPEvent

if TYPE_CHECKING:
    from events.bus import EventBus
    from orchestrator.session_state import SessionStateStore


class EventHandler(Protocol):
    """Handler contract: react to one event type and advance the pipeline."""

    name: str

    def handles(self) -> set[str]:
        """Event type strings this handler listens to."""
        ...

    def handle(
        self,
        event: MCPEvent,
        store: SessionStateStore,
        bus: EventBus,
    ) -> None:
        ...


class EventDispatcher:
    """
    Fixed-flow orchestrator: events mark lifecycle transitions.

    Handlers are invoked synchronously from a queue so nested publishes
    (e.g. RequirementsCompleted during RequirementsHandler) are processed
    in order without unbounded recursion.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}
        self._queue: deque[MCPEvent] = deque()
        self._processing = False
        self._handled_keys: set[str] = set()

    def register(self, handler: EventHandler) -> None:
        for event_type in handler.handles():
            self._handlers.setdefault(event_type, []).append(handler)

    def enqueue(self, event: MCPEvent, *, store: SessionStateStore, bus: EventBus) -> None:
        self._queue.append(event)
        if not self._processing:
            self._drain(store, bus)

    def _drain(self, store: SessionStateStore, bus: EventBus) -> None:
        self._processing = True
        try:
            while self._queue:
                event = self._queue.popleft()
                for handler in self._handlers.get(event.type, []):
                    key = f"{handler.name}:{event.type}:{event.sequence}"
                    if key in self._handled_keys:
                        continue
                    self._handled_keys.add(key)
                    handler.handle(event, store, bus)
        finally:
            self._processing = False

    def reset(self) -> None:
        self._queue.clear()
        self._handled_keys.clear()
