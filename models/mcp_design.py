"""
MCPDesign and GeneratedMCP Pydantic models.

These models represent the technical design and the final generated artifact
produced by the MCP Design Agent and MCP Creator Agent.
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field
from models.mcp_requirement import MCPRequirement


class ToolImplementation(BaseModel):
    """Fully resolved implementation for a single @mcp.tool()."""
    name: str
    signature: str           # e.g. "product_id: str, quantity: int = 1"
    return_type: str         # e.g. "dict"
    description: str
    returns_description: str
    body: str                # indented Python code for the function body


class ResourceImplementation(BaseModel):
    """Fully resolved implementation for a single @mcp.resource()."""
    uri_template: str        # e.g. "data://products/{product_id}"
    name: str
    params_signature: str = ""   # e.g. "product_id: str"
    return_type: str = "str"
    description: str
    body: str                # indented Python code for the function body


class MCPDesign(BaseModel):
    """
    Technical design produced by the MCP Design Agent.
    Contains all the resolved implementation details needed to render the templates.
    """
    requirement: MCPRequirement
    server_filename: str                          # e.g. "ecommerce_tools_server.py"
    imports: list[str] = Field(default_factory=list)   # full import statements
    tools: list[ToolImplementation] = Field(default_factory=list)
    resources: list[ResourceImplementation] = Field(default_factory=list)
    has_external_calls: bool = False
    estimated_complexity: Literal["simple", "medium", "complex"] = "simple"


class GeneratedMCP(BaseModel):
    """
    Final artifact: the generated MCP server code and its deployment state.
    """
    design: MCPDesign
    code: str                                     # full Python source of the server
    server_path: str                              # absolute path to written .py file
    status: Literal["generated", "deployed", "error"] = "generated"
    deployment_pid: int | None = None             # process ID if running
    deployment_url: str | None = None             # e.g. "http://localhost:8000" if HTTP
    validation_passed: bool = False
    validation_errors: list[str] = Field(default_factory=list)
