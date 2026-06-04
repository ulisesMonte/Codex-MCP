"""Pipeline error resolution — shared by graph and CLI."""
from __future__ import annotations

from orchestrator.state import MCPFactoryState


def resolve_pipeline_error(state: MCPFactoryState) -> str:
    err = state.get("error")
    if err:
        return str(err)
    generated = state.get("generated_mcp")
    if generated and generated.validation_errors:
        lines = "\n".join(f"• {e}" for e in generated.validation_errors)
        return f"Generated code validation failed:\n{lines}"
    return "Unknown pipeline error. Check events or generated/mcps/."
