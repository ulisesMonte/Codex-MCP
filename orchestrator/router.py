"""
Router — conditional edge logic for the LangGraph StateGraph.
"""
from __future__ import annotations

from langgraph.graph import END
from langgraph.types import Send

from config.constants import MAX_VALIDATION_RETRIES
from orchestrator.state import MCPFactoryState

MAX_RETRIES = MAX_VALIDATION_RETRIES


def route_after_requirements(state: MCPFactoryState):
    """
    After requirements:
    - gathering → END (wait for user)
    - complete  → fan-out to 4 parallel scout agents
    """
    if state.get("phase") != "complete":
        return END

    return [
        Send("scout_mcp_agent", state),
        Send("scout_api_agent", state),
        Send("scout_data_agent", state),
        Send("scout_docs_agent", state),
    ]


def route_after_validation(state: MCPFactoryState) -> str:
    generated = state.get("generated_mcp")
    attempts = state.get("validation_attempts", 0)

    if generated and generated.validation_passed:
        return "deployer"

    if attempts < MAX_RETRIES:
        return "mcp_creator_agent"

    return "error_handler"


def route_after_deployer(state: MCPFactoryState) -> str:
    error = state.get("error")
    if error:
        return "error_handler"
    return "registry_updater"
