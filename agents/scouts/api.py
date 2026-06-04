"""Scout agent — API / REST / microservice repos."""
from __future__ import annotations

from typing import TYPE_CHECKING

from agents.scouts.base import scout_agent_node

if TYPE_CHECKING:
    from orchestrator.state import MCPFactoryState


def scout_api_agent_node(state: "MCPFactoryState") -> "MCPFactoryState":
    return scout_agent_node(state, "api")
