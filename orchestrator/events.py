"""Helpers for publishing pipeline events from LangGraph nodes."""
from __future__ import annotations

from typing import Any

from events.model import EventLevel
from events.runtime import get_event_bus
from orchestrator.state import MCPFactoryState


def publish_event(
    state: MCPFactoryState,
    type: str,
    source: str,
    message: str,
    level: EventLevel = "info",
    payload: dict[str, Any] | None = None,
) -> None:
    session_id = state.get("session_id")
    if not session_id:
        return
    get_event_bus(session_id).publish(
        type=type,
        source=source,
        level=level,
        message=message,
        payload=payload,
    )
