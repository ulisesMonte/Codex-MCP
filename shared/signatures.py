"""Parameter signature helpers for codegen."""
from __future__ import annotations

from models.mcp_requirement import ParameterSpec


def params_to_signature(params: list[ParameterSpec]) -> str:
    parts: list[str] = []
    for p in params:
        ptype = p.type or "str"
        if p.required:
            parts.append(f"{p.name}: {ptype}")
        else:
            default = repr(p.default) if isinstance(p.default, str) else str(p.default)
            parts.append(f"{p.name}: {ptype} = {default}")
    return ", ".join(parts)
