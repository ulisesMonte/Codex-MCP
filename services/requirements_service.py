"""Orchestrates requirements gathering domain logic for the agent node."""
from __future__ import annotations

from dataclasses import dataclass

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from domain.requirements.conversation import ConversationSignals, RequirementLifecycle
from domain.requirements.enricher import RequirementEnricher
from domain.requirements.merger import RequirementMerger
from domain.session import MCPFactorySession
from models.mcp_requirement import MCPRequirement
from requirements.response import parse_requirements_response


@dataclass
class RequirementsTurnResult:
    """Result of processing one requirements-gathering turn."""

    requirement: MCPRequirement
    message_to_user: str
    status: str
    parse_ok: bool
    llm_hints: list[SystemMessage]


class RequirementsService:
    """Application service: LLM response → enriched requirement + user message."""

    def __init__(
        self,
        merger: RequirementMerger | None = None,
        enricher: RequirementEnricher | None = None,
        lifecycle: RequirementLifecycle | None = None,
        signals: ConversationSignals | None = None,
    ) -> None:
        self.signals = signals or ConversationSignals()
        self.merger = merger or RequirementMerger()
        self.enricher = enricher or RequirementEnricher(intent_resolver=None, signals=self.signals)
        self.lifecycle = lifecycle or RequirementLifecycle(self.signals)

    def build_llm_hints(self, session: MCPFactorySession) -> list[SystemMessage]:
        """System hints injected before the LLM call based on user signals."""
        hints: list[SystemMessage] = []
        last_user = session.last_user_message()

        if last_user and self.signals.user_sent_tool_correction(last_user):
            hints.append(
                SystemMessage(
                    content=(
                        "[HINT] The user is CORRECTING tool names/count in their last message. "
                        "Replace current_requirement.tools completely from their correction. "
                        "Do NOT repeat a single-tool summary. Reflect ALL tools they named."
                    )
                )
            )
        elif last_user and self.signals.user_rejects_proposal(last_user):
            hints.append(
                SystemMessage(
                    content=(
                        "[HINT] The user REJECTED your last proposal. Read their correction carefully, "
                        "REPLACE current_requirement.tools with exactly what they asked for, "
                        "fix mcp_name/description, clear clarifications_needed, and ask for confirmation again. "
                        "Do NOT set status=complete."
                    )
                )
            )
        elif last_user and self.signals.is_affirmative(last_user):
            hints.append(
                SystemMessage(
                    content=(
                        "[HINT] The user's last message is an affirmative short answer (sí/yes/ok). "
                        "Apply it to your previous question or proposal, update current_requirement with the "
                        "tools/names you suggested, clear clarifications_needed, and move toward confirmation "
                        "— do not repeat the question."
                    )
                )
            )
        return hints

    def process_turn(
        self,
        raw_llm_response: str,
        session: MCPFactorySession,
    ) -> RequirementsTurnResult:
        messages = session.messages
        current = session.requirement
        user_text = self.signals.combined_user_text(messages)
        last_user = session.last_user_message()

        message_to_user, llm_status, req_data, parse_ok = parse_requirements_response(
            raw_llm_response, current
        )
        updated = self.merger.merge(req_data, current)
        updated = self.enricher.enrich(updated, user_text, messages)
        updated = self.enricher.finalize(updated, messages)
        status = self.lifecycle.decide_status(updated, llm_status, last_user, messages)

        if updated.is_ready():
            message_to_user = self.lifecycle.build_confirmation_message(updated)
        elif not message_to_user or message_to_user.strip().startswith("{"):
            if updated.tools:
                message_to_user = self.lifecycle.build_confirmation_message(updated)

        return RequirementsTurnResult(
            requirement=updated,
            message_to_user=message_to_user,
            status=status,
            parse_ok=parse_ok,
            llm_hints=[],
        )
