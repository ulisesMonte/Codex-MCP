"""Small protocols for event infrastructure dependencies."""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from events.model import MCPEvent

EventSubscriber = Callable[[MCPEvent], None]


class EventStore(Protocol):
    """Persistence contract required by EventBus."""

    def append(self, event: MCPEvent) -> None:
        ...

    def read_session(self, session_id: str) -> list[MCPEvent]:
        ...

    def list_sessions(self) -> list[str]:
        ...

    def next_sequence(self, session_id: str) -> int:
        ...
