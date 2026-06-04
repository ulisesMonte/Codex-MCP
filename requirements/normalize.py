"""Normalize LLM requirement payloads before Pydantic validation."""
from __future__ import annotations

from typing import Any


def normalize_clarifications(raw: Any) -> list[str]:
    """LLMs sometimes return objects like {"question": "...", "type": "open"}."""
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if not isinstance(raw, list):
        raw = [raw]

    out: list[str] = []
    for item in raw:
        text = _clarification_to_string(item)
        if text:
            out.append(text)
    return out


def _clarification_to_string(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in ("question", "text", "message", "prompt", "item", "description", "label"):
            val = item.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return ""
    if item is None:
        return ""
    return str(item).strip()
