"""Parse and normalize Requirements Agent LLM responses."""
from __future__ import annotations

from requirements.enrichment import user_facing_gaps
from llm.json_parse import extract_json
from models.mcp_requirement import MCPRequirement


def parse_requirements_response(
    raw: str,
    current: MCPRequirement | None,
) -> tuple[str, str, dict, bool]:
    """
    Returns (message_to_user, status, requirement_data, parse_ok).
    message_to_user is always non-empty and never raw JSON.
    """
    parsed, parse_ok = extract_json(raw)
    status = str(parsed.get("status", "gathering")).strip().lower()
    if status not in ("gathering", "complete"):
        status = "gathering"

    req_data = parsed.get("current_requirement") or {}
    if not isinstance(req_data, dict):
        req_data = {}

    message_to_user = str(parsed.get("message_to_user") or "").strip()
    if not message_to_user:
        message_to_user = _fallback_message(req_data, current, status)

    return message_to_user, status, req_data, parse_ok


def build_clarification_message(req: MCPRequirement) -> str:
    gaps = user_facing_gaps(req)
    if not gaps:
        return (
            "Almost there — please confirm the MCP name and a short description, "
            "or say **confirm** if the summary looks correct."
        )
    parts = gaps[:5]
    return _format_clarification(parts)


def _fallback_message(req_data: dict, current: MCPRequirement | None, status: str) -> str:
    merged = _merge_for_fallback(req_data, current)
    gaps = user_facing_gaps(merged)
    if gaps:
        return _format_clarification(gaps[:5])
    if merged.mcp_name:
        return (
            f"Working on **{merged.mcp_name}**. "
            "Reply with more details or say **confirm** when ready."
        )
    return (
        "Tell me what MCP you need (data source, API, or workflow). "
        "I'll propose tools and parameters."
    )


def _format_clarification(parts: list[str]) -> str:
    if not parts:
        return ""
    lines = ["Necesito estas aclaraciones:", ""]
    for i, p in enumerate(parts, 1):
        lines.append(f"{i}. {p}")
    return "\n".join(lines)


def _merge_for_fallback(req_data: dict, current: MCPRequirement | None) -> MCPRequirement:
    """Light merge only for fallback messaging (full merge is in requirements_merge)."""
    if not req_data and current:
        return current
    name = req_data.get("mcp_name") or (current.mcp_name if current else "")
    desc = req_data.get("description") or (current.description if current else "")
    clar = req_data.get("clarifications_needed") or (
        current.clarifications_needed if current else []
    )
    return MCPRequirement(
        mcp_name=name or "",
        description=desc or "",
        clarifications_needed=clar if isinstance(clar, list) else [],
    )


def _looks_like_json_blob(text: str) -> bool:
    s = text.strip()
    if s.startswith("{") and "current_requirement" in s:
        return True
    if s.startswith("```"):
        return True
    return len(s) > 400 and '"mcp_name"' in s
