"""LangChain message helpers shared across agents and CLI."""
from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


def last_agent_message(messages: list[BaseMessage]) -> str | None:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            text = str(msg.content).strip()
            if text and not text.startswith("{"):
                return text
    return None


def last_user_message(messages: list[BaseMessage]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage) and msg.content:
            return str(msg.content).strip()
    return ""
