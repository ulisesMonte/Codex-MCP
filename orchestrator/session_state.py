"""In-memory session state projection for event-driven orchestration."""
from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage

from orchestrator.state import MCPFactoryState


class SessionStateStore:
    """Mutable pipeline state keyed by session_id (RAM projection of the event log)."""

    def __init__(self) -> None:
        self._states: dict[str, MCPFactoryState] = {}

    def get(self, session_id: str) -> MCPFactoryState:
        return dict(self._states.get(session_id, {}))

    def init(self, session_id: str, state: MCPFactoryState) -> MCPFactoryState:
        merged = self._merge({}, state)
        merged["session_id"] = session_id
        self._states[session_id] = merged
        return merged

    def update(self, session_id: str, updates: MCPFactoryState) -> MCPFactoryState:
        current = self._states.get(session_id, {})
        merged = self._merge(current, updates)
        merged["session_id"] = session_id
        self._states[session_id] = merged
        return merged

    def snapshot(self, session_id: str) -> MCPFactoryState:
        return dict(self._states.get(session_id, {}))

    def _merge(self, base: MCPFactoryState, updates: MCPFactoryState) -> MCPFactoryState:
        result: dict[str, Any] = dict(base)
        for key, value in updates.items():
            if value is None and key not in ("requirement", "design", "generated_mcp", "error"):
                continue
            if key == "scout_reports" and value:
                existing = list(result.get("scout_reports") or [])
                incoming = value if isinstance(value, list) else [value]
                result[key] = existing + incoming
            elif key == "messages" and value is not None:
                result[key] = value
            else:
                result[key] = value
        return result  # type: ignore[return-value]


_GLOBAL_STORE = SessionStateStore()


def get_session_state_store() -> SessionStateStore:
    return _GLOBAL_STORE
