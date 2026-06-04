"""User conversation signals — delegates to domain model."""
from __future__ import annotations

from langchain_core.messages import BaseMessage

from domain.requirements.conversation import ConversationSignals

_signals = ConversationSignals()


def combined_user_text(messages: list[BaseMessage]) -> str:
    return _signals.combined_user_text(messages)


def user_confirmed(text: str) -> bool:
    return _signals.user_confirmed(text)


def is_affirmative(text: str) -> bool:
    return _signals.is_affirmative(text)


def user_accepts_proposal(text: str) -> bool:
    return _signals.user_accepts_proposal(text)


def user_rejects_proposal(text: str) -> bool:
    return _signals.user_rejects_proposal(text)


def agent_asked_confirmation(messages: list[BaseMessage]) -> bool:
    return _signals.agent_asked_confirmation(messages)


def user_sent_tool_correction(text: str) -> bool:
    return _signals.user_sent_tool_correction(text)
