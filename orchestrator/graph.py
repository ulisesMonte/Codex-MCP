"""
LangGraph StateGraph — MCP Factory pipeline with parallel scout agents.

Flow:
  requirements → (4 scouts in parallel) → scout_validator → design → creator → ...
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from orchestrator.state import MCPFactoryState
from orchestrator.router import (
    route_after_requirements,
    route_after_validation,
    route_after_deployer,
)
from agents.requirements import requirements_agent_node
from agents.scouts.mcp import scout_mcp_agent_node
from agents.scouts.api import scout_api_agent_node
from agents.scouts.data import scout_data_agent_node
from agents.scouts.docs import scout_docs_agent_node
from agents.scouts.validator import scout_validator_agent_node
from agents.design import mcp_design_agent_node
from agents.creator import mcp_creator_agent_node
from agents.validator import validator_agent_node
from deployer.local_deployer import deployer_node
from events.types import EventTypes
from orchestrator.events import publish_event
from orchestrator.pipeline_errors import resolve_pipeline_error
from registry.registry_manager import registry_updater_node


def error_handler_node(state: MCPFactoryState) -> MCPFactoryState:
    from rich.console import Console
    from rich.panel import Panel
    console = Console()
    error = resolve_pipeline_error(state)
    attempts = state.get("validation_attempts", 0)
    publish_event(
        state,
        EventTypes.PIPELINE_FAILED,
        "error_handler",
        "Pipeline failed",
        level="error",
        payload={"error": error, "validation_attempts": attempts},
    )
    console.print()
    console.print(
        Panel(
            f"[red]Pipeline failed after {attempts} attempt(s).[/red]\n\n"
            f"[yellow]Reason:[/yellow] {error}\n\n"
            "You can restart with a new request.",
            title="[bold red]❌ MCP Factory — Error[/bold red]",
            border_style="red",
        )
    )
    return {**state, "phase": "error", "error": error}


def build_graph() -> StateGraph:
    graph = StateGraph(MCPFactoryState)

    graph.add_node("requirements_agent", requirements_agent_node)
    graph.add_node("scout_mcp_agent", scout_mcp_agent_node)
    graph.add_node("scout_api_agent", scout_api_agent_node)
    graph.add_node("scout_data_agent", scout_data_agent_node)
    graph.add_node("scout_docs_agent", scout_docs_agent_node)
    graph.add_node("scout_validator_agent", scout_validator_agent_node)
    graph.add_node("mcp_design_agent", mcp_design_agent_node)
    graph.add_node("mcp_creator_agent", mcp_creator_agent_node)
    graph.add_node("validator_agent", validator_agent_node)
    graph.add_node("deployer", deployer_node)
    graph.add_node("registry_updater", registry_updater_node)
    graph.add_node("error_handler", error_handler_node)

    graph.set_entry_point("requirements_agent")

    graph.add_conditional_edges("requirements_agent", route_after_requirements)

    for scout in ("scout_mcp_agent", "scout_api_agent", "scout_data_agent", "scout_docs_agent"):
        graph.add_edge(scout, "scout_validator_agent")

    graph.add_edge("scout_validator_agent", "mcp_design_agent")

    graph.add_conditional_edges(
        "validator_agent",
        route_after_validation,
        {
            "deployer": "deployer",
            "mcp_creator_agent": "mcp_creator_agent",
            "error_handler": "error_handler",
        },
    )

    graph.add_conditional_edges(
        "deployer",
        route_after_deployer,
        {
            "registry_updater": "registry_updater",
            "error_handler": "error_handler",
        },
    )

    graph.add_edge("mcp_design_agent", "mcp_creator_agent")
    graph.add_edge("mcp_creator_agent", "validator_agent")
    graph.add_edge("registry_updater", END)
    graph.add_edge("error_handler", END)

    memory = MemorySaver(
        serde=JsonPlusSerializer(
            allowed_msgpack_modules=[
                ("models.mcp_requirement", "OutputMode"),
                ("models.mcp_requirement", "GenerationIntent"),
                ("models.mcp_requirement", "MCPRequirement"),
                ("models.mcp_requirement", "ToolSpec"),
                ("models.mcp_requirement", "ParameterSpec"),
                ("models.mcp_requirement", "ResourceSpec"),
                ("models.mcp_design", "MCPDesign"),
                ("models.mcp_design", "ToolImplementation"),
                ("models.mcp_design", "ResourceImplementation"),
                ("models.mcp_design", "GeneratedMCP"),
            ]
        )
    )
    return graph.compile(checkpointer=memory)
