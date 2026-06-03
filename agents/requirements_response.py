"""Parse and normalize Requirements Agent LLM responses."""
from __future__ import annotations

import json
import re

from agents.requirements_enrichment import user_facing_gaps
from models.mcp_requirement import MCPRequirement


def parse_requirements_response(
    raw: str,
    current: MCPRequirement | None,
) -> tuple[str, str, dict, bool]:
    """
    Returns (message_to_user, status, requirement_data, parse_ok).
    message_to_user is always non-empty and never raw JSON.
    """
    parsed, parse_ok = _extract_json(raw)
    status = str(parsed.get("status", "gathering")).strip().lower()
    if status not in ("gathering", "complete"):
        status = "gathering"

    req_data = parsed.get("current_requirement") or {}
    if not isinstance(req_data, dict):
        req_data = {}

    message = _normalize_message(parsed.get("message_to_user"))
    if not message:
        message = _message_from_clarifications(req_data, current)

    if not message or _looks_like_json_blob(message):
        merged = _merge_for_fallback(req_data, current)
        message = build_clarification_message(merged)

    return message, status, req_data, parse_ok


def build_clarification_message(requirement: MCPRequirement | None) -> str:
    """Fallback message — prefer confirmation over interrogation."""
    if requirement is None:
        return (
            "Contame qué MCP querés crear (en tus palabras). "
            "Yo completo nombre, parámetros y dependencias; vos solo confirmás al final."
        )

    if requirement.is_ready():
        return build_confirmation_message(requirement)

    gaps = user_facing_gaps(requirement)
    if gaps:
        return gaps[0] if len(gaps) == 1 else "\n".join(f"- {g}" for g in gaps)

    return "Contame un poco más qué debe hacer el MCP."


def build_confirmation_message(requirement: MCPRequirement) -> str:
    from agents.requirements_enrichment import build_confirmation_message as _confirm
    return _confirm(requirement)


def _normalize_message(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    # Model sometimes puts markdown headers instead of prose
    if text.startswith("**Requisitos") or text.startswith("# "):
        return ""
    return text


def _message_from_clarifications(req_data: dict, current: MCPRequirement | None) -> str:
    notes = req_data.get("clarifications_needed") or []
    if not isinstance(notes, list):
        return ""
    parts = [str(n).strip() for n in notes if str(n).strip()]
    if not parts and current:
        parts = [str(n).strip() for n in current.clarifications_needed if str(n).strip()]
    if not parts:
        return ""
    lines = ["Necesito estas aclaraciones:", ""]
    for i, p in enumerate(parts, 1):
        lines.append(f"{i}. {p}")
    return "\n".join(lines)


def _merge_for_fallback(req_data: dict, current: MCPRequirement | None) -> MCPRequirement:
    """Light merge only for fallback messaging (full merge is in requirements_agent)."""
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


def _extract_json(text: str) -> tuple[dict, bool]:
    text = text.strip()
    candidates = [text]

    for pattern in (r"```json\s*([\s\S]*?)\s*```", r"```\s*([\s\S]*?)\s*```"):
        m = re.search(pattern, text, re.DOTALL)
        if m:
            candidates.insert(0, m.group(1).strip())

    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        candidates.append(m.group(0))

    for candidate in candidates:
        for loader in (_loads_strict, _loads_relaxed):
            try:
                data = loader(candidate)
                if isinstance(data, dict):
                    return data, True
            except (json.JSONDecodeError, ValueError):
                continue

    partial = _regex_extract_fields(text)
    if partial:
        return partial, False

    return {}, False


def _loads_strict(s: str) -> dict:
    return json.loads(s)


def _loads_relaxed(s: str) -> dict:
    fixed = re.sub(r",\s*}", "}", s)
    fixed = re.sub(r",\s*]", "]", fixed)
    return json.loads(fixed)


def _regex_extract_fields(text: str) -> dict:
    """Best-effort extraction when JSON is malformed."""
    out: dict = {}
    m = re.search(
        r'"message_to_user"\s*:\s*"((?:[^"\\]|\\.)*)"',
        text,
        re.DOTALL,
    )
    if m:
        out["message_to_user"] = bytes(m.group(1), "utf-8").decode("unicode_escape")

    status_m = re.search(r'"status"\s*:\s*"(gathering|complete)"', text)
    if status_m:
        out["status"] = status_m.group(1)

    block = re.search(r'"current_requirement"\s*:\s*(\{[\s\S]*?\})\s*[,}]', text)
    if block:
        try:
            out["current_requirement"] = json.loads(block.group(1))
        except json.JSONDecodeError:
            pass

    return out
