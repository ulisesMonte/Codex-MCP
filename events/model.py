"""Typed event model for append-only MCP Factory logs."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


EventLevel = Literal["debug", "info", "warning", "error"]


class MCPEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    sequence: int
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    type: str
    source: str
    level: EventLevel = "info"
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
