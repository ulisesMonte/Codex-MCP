"""Merge partial LLM requirement payloads into MCPRequirement."""
from __future__ import annotations

from models.mcp_requirement import (
    GenerationIntent,
    MCPRequirement,
    OutputMode,
    ParameterSpec,
    ResourceSpec,
    ToolSpec,
)
from requirements.normalize import normalize_clarifications


class RequirementMerger:
    """Combines incremental requirement dicts from the LLM with the current state."""

    def merge(self, data: dict, current: MCPRequirement | None) -> MCPRequirement:
        if not data:
            return current or MCPRequirement()

        base = current.model_dump() if current else {}

        def get(key: str, fallback=None):
            val = data.get(key)
            return val if val not in (None, "", [], {}) else base.get(key, fallback)

        tools = self._parse_tools(
            data.get("tools") if data.get("tools") else base.get("tools", [])
        )
        resources = self._parse_resources(data.get("resources") or base.get("resources", []))

        try:
            output_mode = OutputMode(
                data.get("output_mode") or base.get("output_mode", "code_only")
            )
        except ValueError:
            output_mode = OutputMode.CODE_ONLY

        clarifications = normalize_clarifications(
            data.get("clarifications_needed")
            if data.get("clarifications_needed") is not None
            else base.get("clarifications_needed", [])
        )

        return MCPRequirement(
            mcp_name=get("mcp_name", ""),
            description=get("description", ""),
            tools=tools,
            resources=resources,
            transport=get("transport", "stdio"),
            dependencies=get("dependencies", []),
            output_mode=output_mode,
            port=get("port", 8000),
            generation_intent=self._parse_generation_intent(data, base),
            is_complete=data.get("is_complete", False),
            clarifications_needed=clarifications,
        )

    def _parse_tools(self, raw_tools: list) -> list[ToolSpec]:
        tools: list[ToolSpec] = []
        for t in raw_tools:
            if isinstance(t, dict):
                params = [
                    ParameterSpec(
                        name=p.get("name", ""),
                        type=p.get("type", "str"),
                        description=p.get("description", ""),
                        required=p.get("required", True),
                        default=p.get("default"),
                    )
                    for p in t.get("parameters", [])
                ]
                tools.append(
                    ToolSpec(
                        name=t.get("name", ""),
                        description=t.get("description", ""),
                        parameters=params,
                        returns_type=t.get("returns_type", "str"),
                        returns_description=t.get("returns_description", ""),
                        implementation_hint=t.get("implementation_hint", ""),
                    )
                )
            elif isinstance(t, ToolSpec):
                tools.append(t)
        return tools

    def _parse_resources(self, raw_res: list) -> list[ResourceSpec]:
        resources: list[ResourceSpec] = []
        for r in raw_res:
            if isinstance(r, dict):
                params = [
                    ParameterSpec(
                        name=p.get("name", ""),
                        type=p.get("type", "str"),
                        description=p.get("description", ""),
                        required=p.get("required", True),
                    )
                    for p in r.get("params", [])
                ]
                resources.append(
                    ResourceSpec(
                        uri_template=r.get("uri_template", ""),
                        name=r.get("name", ""),
                        description=r.get("description", ""),
                        returns_type=r.get("returns_type", "str"),
                        mime_type=r.get("mime_type", "text/plain"),
                        has_params=len(params) > 0,
                        params=params,
                    )
                )
            elif isinstance(r, ResourceSpec):
                resources.append(r)
        return resources

    @staticmethod
    def _parse_generation_intent(data: dict, base: dict) -> GenerationIntent:
        raw = data.get("generation_intent") or base.get("generation_intent", "auto")
        try:
            return GenerationIntent(raw)
        except ValueError:
            return GenerationIntent.AUTO


_default_merger = RequirementMerger()


def merge_requirement(data: dict, current: MCPRequirement | None) -> MCPRequirement:
    return _default_merger.merge(data, current)
