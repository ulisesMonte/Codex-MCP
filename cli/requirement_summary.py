"""Human-readable requirement snapshot (no raw JSON)."""
from __future__ import annotations

from models.mcp_requirement import MCPRequirement, OutputMode


def format_requirement_snapshot(req: MCPRequirement) -> str:
    """Markdown summary for the chat panel."""
    lines: list[str] = []

    if req.mcp_name:
        lines.append(f"**MCP:** `{req.mcp_name}`")
    if req.description:
        lines.append(f"**Description:** {req.description}")

    if req.tools:
        lines.append("")
        lines.append("**Tools:**")
        for t in req.tools:
            params = ", ".join(
                f"{p.name}: {p.type}" + ("?" if not p.required else "")
                for p in t.parameters
            )
            sig = f"{t.name}({params})" if params else f"{t.name}()"
            lines.append(f"- `{sig}` — {t.description or '(no description)'}")
            if t.returns_type:
                lines.append(f"  - Returns: `{t.returns_type}` — {t.returns_description or '—'}")

    if req.resources:
        lines.append("")
        lines.append("**Resources:**")
        for r in req.resources:
            lines.append(f"- `{r.uri_template}` → `{r.name}` — {r.description or '—'}")

    if req.dependencies:
        lines.append("")
        lines.append(f"**Dependencies:** {', '.join(req.dependencies)}")

    mode = req.output_mode.value if isinstance(req.output_mode, OutputMode) else str(req.output_mode)
    lines.append("")
    lines.append(f"**Output:** `{mode}` · **Transport:** `{req.transport}`")

    if not lines:
        return "_No structured data yet — describe the MCP in your first message._"

    return "\n".join(lines)
