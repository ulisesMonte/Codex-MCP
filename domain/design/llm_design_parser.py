"""Parse LLM JSON responses into MCPDesign."""
from __future__ import annotations

from domain.codegen.design_builder import DeterministicDesignBuilder
from models.mcp_design import MCPDesign, ResourceImplementation, ToolImplementation
from models.mcp_requirement import MCPRequirement


class LlmDesignParser:
    """Builds MCPDesign from coder-LLM JSON output."""

    def __init__(self, builder: DeterministicDesignBuilder | None = None) -> None:
        self.builder = builder or DeterministicDesignBuilder()

    def parse(self, req: MCPRequirement, data: dict) -> MCPDesign:
        tools = [
            ToolImplementation(
                name=t.get("name", ""),
                signature=t.get("signature", ""),
                return_type=t.get("return_type", "str"),
                description=t.get("description", ""),
                returns_description=t.get("returns_description", ""),
                body=self.normalize_body(t.get("body", "")),
            )
            for t in data.get("tools", [])
            if t.get("name")
            and not self.builder.is_weak_tool(
                ToolImplementation(
                    name=t.get("name", ""),
                    signature=t.get("signature", ""),
                    return_type="str",
                    description="",
                    returns_description="",
                    body=self.normalize_body(t.get("body", "")),
                )
            )
        ]
        if not tools:
            return self.builder.build(req)

        resources = [
            ResourceImplementation(
                uri_template=r.get("uri_template", ""),
                name=r.get("name", ""),
                params_signature=r.get("params_signature", ""),
                return_type=r.get("return_type", "str"),
                description=r.get("description", ""),
                body=self.normalize_body(r.get("body", '    return "ok"')),
            )
            for r in data.get("resources", [])
        ]
        return MCPDesign(
            requirement=req,
            server_filename=data.get("server_filename", f"{req.mcp_name}_server.py"),
            imports=data.get("imports", []),
            tools=tools,
            resources=resources,
            has_external_calls=data.get("has_external_calls", False),
            estimated_complexity=data.get("estimated_complexity", "simple"),
        )

    @staticmethod
    def normalize_body(body: str) -> str:
        if not body:
            return ""
        body = body.replace("\\n", "\n").replace("\\t", "\t")
        lines = body.splitlines()
        normalized: list[str] = []
        for line in lines:
            s = line.rstrip()
            if s and not s.startswith((" ", "\t")):
                normalized.append(f"    {s}")
            else:
                normalized.append(s)
        return "\n".join(normalized)


def normalize_body(body: str) -> str:
    return LlmDesignParser.normalize_body(body)
