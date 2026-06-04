"""Requirement enrichment pipeline — delegates to domain models."""
from __future__ import annotations

from langchain_core.messages import BaseMessage

from domain.requirements.conversation import RequirementLifecycle
from domain.requirements.enricher import RequirementEnricher
from models.mcp_requirement import MCPRequirement

_enricher = RequirementEnricher()
_lifecycle = RequirementLifecycle()


def enrich_requirement(
    req: MCPRequirement,
    user_text: str,
    messages: list[BaseMessage] | None = None,
) -> MCPRequirement:
    return _enricher.enrich(req, user_text, messages)


def finalize_requirement(req: MCPRequirement, messages: list[BaseMessage]) -> MCPRequirement:
    return _enricher.finalize(req, messages)


def build_confirmation_message(req: MCPRequirement) -> str:
    return _lifecycle.build_confirmation_message(req)


def user_facing_gaps(req: MCPRequirement) -> list[str]:
    return _lifecycle.user_facing_gaps(req)


def decide_status(
    req: MCPRequirement,
    llm_status: str,
    last_user_message: str,
    messages: list[BaseMessage] | None = None,
) -> str:
    return _lifecycle.decide_status(req, llm_status, last_user_message, messages)
