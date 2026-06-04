"""Deterministic MCP design building from requirements."""
from __future__ import annotations

from codegen.factory import (
    build_microservice_factory_design,
    is_microservice_factory_requirement,
)
from models.mcp_design import MCPDesign, ResourceImplementation, ToolImplementation
from models.mcp_requirement import MCPRequirement, ToolSpec
from shared.parallel import map_agent_tasks


class DeterministicDesignBuilder:
    """Builds MCPDesign without LLM — domain-aware tool bodies and merge policy."""

    PARALLEL_TOOL_THRESHOLD = 2

    def build(self, req: MCPRequirement) -> MCPDesign:
        if is_microservice_factory_requirement(req):
            return build_microservice_factory_design(req)

        from codegen.router import (
            build_resource_implementation,
            imports_for_requirement,
        )
        from codegen.tool_bodies import tool_domain

        if len(req.tools) > self.PARALLEL_TOOL_THRESHOLD:
            tools = map_agent_tasks(lambda t: self.build_tool(t, req), req.tools)
        else:
            tools = [self.build_tool(t, req) for t in req.tools]

        resources = [self.build_resource(r) for r in req.resources]
        has_external = any(
            tool_domain(t, req) in ("bigquery", "database", "http") for t in req.tools
        )

        return MCPDesign(
            requirement=req,
            server_filename=f"{req.mcp_name}_server.py",
            imports=imports_for_requirement(req),
            tools=tools,
            resources=resources,
            has_external_calls=has_external,
            estimated_complexity="medium" if has_external else "simple",
        )

    def build_tool(self, tool: ToolSpec, req: MCPRequirement) -> ToolImplementation:
        from codegen.router import build_tool_implementation

        return build_tool_implementation(tool, req)

    def build_resource(self, resource) -> ResourceImplementation:
        from codegen.router import build_resource_implementation

        return build_resource_implementation(resource)

    def merge(self, baseline: MCPDesign, candidate: MCPDesign) -> MCPDesign:
        from codegen.router import merge_designs

        return merge_designs(baseline, candidate)

    def is_weak_tool(self, tool: ToolImplementation) -> bool:
        from codegen.router import is_weak_tool_implementation

        return is_weak_tool_implementation(tool)

    def module_helpers(self, req: MCPRequirement) -> str:
        from codegen.router import get_module_helpers

        return get_module_helpers(req)
