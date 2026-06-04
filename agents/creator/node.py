"""
MCP Creator Agent — generates the final Python source code for the MCP server.
"""
from __future__ import annotations

from pathlib import Path

from typing import TYPE_CHECKING

from domain.session import MCPFactorySession
from events.types import EventTypes
from orchestrator.events import publish_event
from services.creator_service import CreatorService
from shared.progress import agent_note

if TYPE_CHECKING:
    from orchestrator.state import MCPFactoryState

_creator_service = CreatorService()

# Re-exports for tests and backward compatibility
_render_code = _creator_service.render_code
_has_fastmcp_structure = CreatorService.has_fastmcp_structure
_errors_are_structural = CreatorService.errors_are_structural


def mcp_creator_agent_node(state: "MCPFactoryState") -> "MCPFactoryState":
    session = MCPFactorySession(state)
    design = session.design
    if design is None:
        return {**state, "error": "No design in state"}

    attempt = session.validation_attempts
    agent_note(
        f"Creator — generando {design.server_filename}"
        + (f" (retry {attempt}/{3})" if attempt > 0 else "")
    )

    publish_event(
        state,
        EventTypes.CODE_GENERATION_STARTED,
        "mcp_creator_agent",
        "Generating MCP server code",
        payload={"attempt": attempt, "server_filename": design.server_filename},
    )

    prev_errors: list[str] = []
    if attempt > 0 and session.generated_mcp:
        prev_errors = list(session.generated_mcp.validation_errors)
        if prev_errors and not CreatorService.errors_are_structural(prev_errors):
            publish_event(
                state,
                EventTypes.CODE_REPAIR_STARTED,
                "mcp_creator_agent",
                "Repairing generated code from validator feedback",
                payload={"attempt": attempt, "errors": prev_errors},
            )

    try:
        result = _creator_service.generate(session)
        agent_note(f"Código escrito → {Path(result.generated.server_path).name}")
        publish_event(
            state,
            EventTypes.CODE_GENERATED,
            "mcp_creator_agent",
            "MCP server code generated",
            payload={
                "server_path": result.generated.server_path,
                "code_lines": len(result.generated.code.splitlines()),
            },
        )
        return {
            **state,
            "generated_mcp": result.generated,
            "design": result.active_design,
            "error": None,
        }
    except Exception as e:
        agent_note(f"Creator falló: {e}")
        publish_event(
            state,
            EventTypes.CODE_GENERATION_FAILED,
            "mcp_creator_agent",
            "Code generation failed",
            level="error",
            payload={"error": str(e), "server_filename": design.server_filename},
        )
        return {**state, "error": str(e)}
