"""
MCP Design Agent — converts MCPRequirement into MCPDesign.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from domain.design.llm_design_parser import normalize_body as _normalize_body
from domain.session import MCPFactorySession
from events.types import EventTypes
from orchestrator.events import publish_event
from services.design_service import DesignService
from shared.progress import agent_note

if TYPE_CHECKING:
    from orchestrator.state import MCPFactoryState

_design_service = DesignService()


def mcp_design_agent_node(state: "MCPFactoryState") -> "MCPFactoryState":
    session = MCPFactorySession(state)
    req = session.requirement
    if req is None:
        return {**state, "error": "No requirement in state"}

    agent_note(f"Design agent — diseñando {req.mcp_name} ({len(req.tools)} tools)…")
    publish_event(
        state,
        EventTypes.DESIGN_STARTED,
        "mcp_design_agent",
        "Resolving technical MCP design",
        payload={"mcp_name": req.mcp_name},
    )

    result = _design_service.create_design(session)

    agent_note(
        f"Design listo: {len(result.design.tools)} tools"
        + (" (baseline + LLM merge)" if result.llm_used else " (determinístico)")
    )
    publish_event(
        state,
        EventTypes.DESIGN_COMPLETED,
        "mcp_design_agent",
        "Technical design completed",
        payload={
            "server_filename": result.design.server_filename,
            "tools": len(result.design.tools),
            "deterministic_baseline": True,
            "llm_merged": result.llm_used,
        },
    )
    return {**state, "design": result.design, "error": None}
