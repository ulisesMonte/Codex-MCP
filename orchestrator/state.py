"""
MCPFactoryState — shared state for the LangGraph StateGraph.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Optional
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from models.mcp_requirement import MCPRequirement
from models.mcp_design import MCPDesign, GeneratedMCP


class MCPFactoryState(TypedDict, total=False):
    session_id: str

    messages: Annotated[list[BaseMessage], add_messages]

    requirement: Optional[MCPRequirement]
    design: Optional[MCPDesign]
    generated_mcp: Optional[GeneratedMCP]

    # Parallel scout agents append reports (relevadores)
    scout_reports: Annotated[list[dict[str, Any]], operator.add]
    validated_research: Optional[dict[str, Any]]

    phase: str
    validation_attempts: int
    error: Optional[str]
    agent_prompt: Optional[str]
