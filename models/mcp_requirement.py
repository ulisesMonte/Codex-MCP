"""
MCPRequirement and related Pydantic models.

These models represent everything the Requirements Agent needs to collect
from the user before code generation can begin.
"""
from __future__ import annotations

from enum import Enum
import re
from typing import Any, Literal

from pydantic import BaseModel, Field


class OutputMode(str, Enum):
    """How the generated MCP server should be delivered."""
    CODE_ONLY = "code_only"        # Return the Python source file only
    DEPLOY_LOCAL = "deploy_local"  # Launch as local subprocess via stdio
    DEPLOY_HTTP = "deploy_http"    # Launch as HTTP/SSE server


class GenerationIntent(str, Enum):
    """What the MCP tools should do at runtime."""
    AUTO = "auto"                    # Infer from description/tools
    CODE_GENERATOR = "code_generator"  # NL → source code (factories, scaffolds)
    INTEGRATION = "integration"      # Connect/query external systems
    RUNTIME = "runtime"              # Execute operations (CRUD, business logic)


class ParameterSpec(BaseModel):
    """Specification for a single function parameter."""
    name: str
    type: str                      # Python type as string: "str", "int", "list[str]", etc.
    description: str
    required: bool = True
    default: Any = None


class ToolSpec(BaseModel):
    """Specification for a single @mcp.tool() function."""
    name: str                      # snake_case, e.g. "search_product"
    description: str               # clear description for the LLM using this tool
    parameters: list[ParameterSpec] = Field(default_factory=list)
    returns_type: str = "str"      # Python return type as string
    returns_description: str = ""  # what the return value represents
    implementation_hint: str = ""  # optional hint about internal logic


class ResourceSpec(BaseModel):
    """Specification for a single @mcp.resource() endpoint."""
    uri_template: str              # e.g. "data://products/{product_id}"
    name: str                      # snake_case function name
    description: str
    returns_type: Literal["str", "bytes"] = "str"
    mime_type: str = "text/plain"
    has_params: bool = False
    params: list[ParameterSpec] = Field(default_factory=list)


class MCPRequirement(BaseModel):
    """
    Complete requirement for generating an MCP server.
    Built iteratively by the Requirements Agent through conversation.
    is_complete=True only when ALL fields are unambiguous and user has confirmed.
    """
    mcp_name: str = ""             # snake_case, e.g. "ecommerce_tools"
    description: str = ""          # one-sentence description
    tools: list[ToolSpec] = Field(default_factory=list)
    resources: list[ResourceSpec] = Field(default_factory=list)
    transport: Literal["stdio", "http"] = "stdio"
    dependencies: list[str] = Field(default_factory=list)  # pip packages
    output_mode: OutputMode = OutputMode.CODE_ONLY
    port: int = 8000               # only relevant when transport=http
    generation_intent: GenerationIntent = GenerationIntent.AUTO
    is_complete: bool = False
    clarifications_needed: list[str] = Field(default_factory=list)

    def checklist(self) -> dict[str, bool]:
        """Returns completion checklist for each required field."""
        valid_transport = self.transport in ("stdio", "http")
        valid_output_mode = isinstance(self.output_mode, OutputMode)
        http_port_ok = (
            self.output_mode != OutputMode.DEPLOY_HTTP
            or (self.transport == "http" and 1 <= self.port <= 65535)
        )
        has_content = len(self.tools) > 0 or len(self.resources) > 0
        tools_ok = all(
            _is_snake_case(t.name)
            and bool(t.description)
            and bool(t.returns_type)
            and bool(t.returns_description)
            and all(
                _is_snake_case(p.name)
                and bool(p.type)
                and bool(p.description)
                and (p.required or p.default is not None)
                for p in t.parameters
            )
            for t in self.tools
        )
        resources_ok = all(
            bool(r.uri_template)
            and _is_snake_case(r.name)
            and bool(r.description)
            and bool(r.returns_type)
            and (
                not r.has_params
                or all(
                    _is_snake_case(p.name)
                    and bool(p.type)
                    and bool(p.description)
                    for p in r.params
                )
            )
            for r in self.resources
        )
        dependencies_ok = all(isinstance(dep, str) and bool(dep.strip()) for dep in self.dependencies)
        return {
            "mcp_name": _is_snake_case(self.mcp_name),
            "description": bool(self.description),
            "has_tools_or_resources": has_content,
            "tools_complete": tools_ok or len(self.tools) == 0,
            "resources_complete": resources_ok or len(self.resources) == 0,
            "transport_confirmed": valid_transport,
            "dependencies_identified": dependencies_ok,
            "output_mode_confirmed": valid_output_mode,
            "http_port_valid": http_port_ok,
        }

    def is_ready(self) -> bool:
        """True when all checklist items pass."""
        return all(self.checklist().values())

    def missing_fields(self) -> list[str]:
        """Returns list of incomplete checklist items."""
        return [k for k, v in self.checklist().items() if not v]


def _is_snake_case(value: str) -> bool:
    """True for lowercase snake_case identifiers."""
    return bool(re.fullmatch(r"[a-z][a-z0-9_]*", value or ""))
