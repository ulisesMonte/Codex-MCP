"""JSON-safe payload normalization for event logs."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def sanitize_payload(value: Any) -> Any:
    """Convert Pydantic models and nested objects into JSON-safe values."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): sanitize_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
