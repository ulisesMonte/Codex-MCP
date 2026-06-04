"""Requirement enrichment pipeline as a domain object."""
from __future__ import annotations

from langchain_core.messages import BaseMessage

from domain.requirements.intent_resolver import GenerationIntentResolver
from models.mcp_requirement import MCPRequirement
from requirements.enrichment.inference import (
    _apply_contextual_short_answer,
    _apply_domain_context,
    _apply_latest_user_tool_corrections,
    _drop_answered_clarifications,
    _ensure_crud_tools_complete,
    _ensure_microservice_factory_complete,
    _ensure_tool_parameters,
    _fill_tool_defaults,
    _filter_clarifications,
    _infer_dependencies,
    _infer_description,
    _infer_mcp_name,
    _infer_output_mode,
    _infer_tool_names,
    _infer_tools_from_natural_language,
)
from domain.requirements.conversation import ConversationSignals


class RequirementEnricher:
    """Infers technical MCP details from natural-language user input."""

    def __init__(
        self,
        intent_resolver: GenerationIntentResolver | None = None,
        signals: ConversationSignals | None = None,
    ) -> None:
        self.intent = intent_resolver or GenerationIntentResolver()
        self.signals = signals or ConversationSignals()

    def enrich(
        self,
        req: MCPRequirement,
        user_text: str,
        messages: list[BaseMessage] | None = None,
    ) -> MCPRequirement:
        text = user_text or ""
        msgs = messages or []
        req = req.model_copy(deep=True)

        _apply_latest_user_tool_corrections(req, msgs)
        _ensure_crud_tools_complete(req, text, msgs)
        _infer_tools_from_natural_language(req, text)
        _apply_contextual_short_answer(req, msgs)
        _infer_tool_names(req, text)
        _apply_domain_context(req, text)
        _fill_tool_defaults(req)
        _infer_mcp_name(req, text)
        _infer_description(req, text)
        _infer_dependencies(req, text)
        _infer_output_mode(req, text)
        req.clarifications_needed = _filter_clarifications(req.clarifications_needed)
        _drop_answered_clarifications(req, msgs)
        _ensure_microservice_factory_complete(req, text, msgs)
        context = self.signals.combined_user_text(msgs) if msgs else text
        self.intent.apply(req, context)

        return req

    def finalize(
        self,
        req: MCPRequirement,
        messages: list[BaseMessage],
    ) -> MCPRequirement:
        text = self.signals.combined_user_text(messages)
        req = req.model_copy(deep=True)
        _ensure_microservice_factory_complete(req, text, messages)
        _ensure_crud_tools_complete(req, text, messages)
        _ensure_tool_parameters(req)
        _infer_mcp_name(req, text)
        self.intent.apply(req, text)
        return req


_default_enricher = RequirementEnricher()
