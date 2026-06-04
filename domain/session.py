"""Typed facade over MCPFactoryState."""
from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage

from models.mcp_design import GeneratedMCP, MCPDesign
from models.mcp_requirement import MCPRequirement
from models.scout_report import ScoutReport, ValidatedResearch
from orchestrator.state import MCPFactoryState


class MCPFactorySession:
    """Object-oriented view of pipeline state for agents and handlers."""

    def __init__(self, state: MCPFactoryState) -> None:
        self._state = state

    @property
    def session_id(self) -> str:
        return self._state.get("session_id", "default")

    @property
    def phase(self) -> str:
        return self._state.get("phase", "gathering")

    @property
    def messages(self) -> list[BaseMessage]:
        return list(self._state.get("messages") or [])

    @property
    def requirement(self) -> MCPRequirement | None:
        return self._state.get("requirement")

    @property
    def design(self) -> MCPDesign | None:
        return self._state.get("design")

    @property
    def generated_mcp(self) -> GeneratedMCP | None:
        return self._state.get("generated_mcp")

    @property
    def validation_attempts(self) -> int:
        return int(self._state.get("validation_attempts") or 0)

    @property
    def error(self) -> str | None:
        err = self._state.get("error")
        return str(err) if err else None

    @property
    def agent_prompt(self) -> str:
        return str(self._state.get("agent_prompt") or "")

    def last_user_message(self) -> str:
        for msg in reversed(self.messages):
            if isinstance(msg, HumanMessage) and msg.content:
                return str(msg.content).strip()
        return ""

    def scout_reports(self) -> list[ScoutReport]:
        raw = self._state.get("scout_reports") or []
        out: list[ScoutReport] = []
        for item in raw:
            if isinstance(item, ScoutReport):
                out.append(item)
            elif isinstance(item, dict):
                out.append(ScoutReport.model_validate(item))
        return out

    def validated_research(self) -> ValidatedResearch | None:
        raw = self._state.get("validated_research")
        if raw is None:
            return None
        if isinstance(raw, ValidatedResearch):
            return raw
        if isinstance(raw, dict):
            return ValidatedResearch.model_validate(raw)
        return None

    def raw(self) -> MCPFactoryState:
        return dict(self._state)

    def apply(self, updates: MCPFactoryState) -> MCPFactoryState:
        merged = {**self._state, **updates}
        self._state = merged
        return merged

    def to_dict(self) -> dict[str, Any]:
        return dict(self._state)
