"""
Requirements Agent — inference-first gathering; user confirms, agents fill details.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, SystemMessage

from domain.session import MCPFactorySession
from events.types import EventTypes
from llm.ollama_client import get_orchestrator_llm
from llm.stream_invoke import invoke_llm_with_progress
from orchestrator.events import publish_event
from services.requirements_service import RequirementsService

if TYPE_CHECKING:
    from orchestrator.state import MCPFactoryState

_requirements_service = RequirementsService()

SYSTEM_PROMPT = """You are an MCP requirements analyst. The USER speaks casually; YOU fill technical details.

PHILOSOPHY:
- Infer snake_case names, parameter types, return types, dependencies, and auth patterns from context.
- NEVER ask the user for Client IDs, API keys, credentials, or low-level Python types — use env vars / defaults in implementation_hint.
- Ask the user at most ONE short question per turn, only if intent is truly ambiguous.
- When you have enough to implement (name + what it does + tools/resources), set a full current_requirement and ask for CONFIRMATION in message_to_user (not more fields).
- status="complete" ONLY if the user explicitly wrote confirm/confirmar in their LAST message (not a bare sí/yes answering a clarification).
- If the user answers sí/yes/ok to your last question, UPDATE current_requirement accordingly and DO NOT repeat the same question.
- Infer tools dynamically from ANY domain (microservices, DB connections, APIs, auth, exports, etc.) — never assume a fixed template.
- When the user CORRECTS tool count or names in their LAST message, REPLACE tools entirely — never repeat your previous wrong summary.
- If the user lists names like controller_factory, services_factory, repository_factory — create exactly those three tools.

DEFAULTS YOU SHOULD APPLY (do not ask the user):
- output_mode: code_only unless they asked to run/deploy
- transport: stdio
- returns_type: str or list[dict] as appropriate
- returns_description: infer from tool purpose
- dependencies: infer (e.g. google-cloud-bigquery if BigQuery mentioned)
- parameters: [] if user said no parameters

message_to_user style:
- Summarize what YOU understood in plain language.
- End with: "¿Confirmás? Escribí confirm" when ready.
- Example: "Entendí un MCP con tool source_connection que lee BigQuery dataset info, tabla source, proyecto test. ¿Confirmás?"

OUTPUT: single JSON object only, no markdown fences.

{
  "status": "gathering",
  "message_to_user": "...",
  "current_requirement": {
    "mcp_name": "",
    "description": "",
    "tools": [],
    "resources": [],
    "transport": "stdio",
    "dependencies": [],
    "output_mode": "code_only",
    "port": 8000,
    "is_complete": false,
    "clarifications_needed": []
  }
}

clarifications_needed: ONLY items the user must decide (never credentials or typing details).
clarifications_needed MUST be a JSON array of plain strings, e.g. ["¿Querés solo el código o deploy?"] — never objects.
"""


def requirements_agent_node(state: "MCPFactoryState") -> "MCPFactoryState":
    session = MCPFactorySession(state)
    publish_event(
        state,
        EventTypes.REQUIREMENTS_STARTED,
        "requirements_agent",
        "Analyzing user requirements",
    )

    llm = get_orchestrator_llm(temperature=0.1, quiet=True)
    llm_messages: list = [SystemMessage(content=SYSTEM_PROMPT)]

    current = session.requirement
    if current:
        ctx = (
            f"\n[CURRENT REQUIREMENT — merge updates]\n"
            f"{current.model_dump_json(indent=2)}\n"
        )
        llm_messages.append(SystemMessage(content=ctx))

    llm_messages.extend(_requirements_service.build_llm_hints(session))
    llm_messages.extend(session.messages)

    raw = invoke_llm_with_progress(llm, llm_messages, label="Requirements agent")
    result = _requirements_service.process_turn(raw, session)

    if not result.parse_ok:
        publish_event(
            state,
            EventTypes.REQUIREMENT_UPDATED,
            "requirements_agent",
            "LLM response parsed with fallback",
            level="warning",
            payload={"parse_ok": False},
        )

    event_type = (
        EventTypes.REQUIREMENTS_COMPLETED
        if result.status == "complete"
        else EventTypes.CLARIFICATION_NEEDED
    )
    publish_event(
        state,
        EventTypes.REQUIREMENT_UPDATED,
        "requirements_agent",
        "Requirement state updated",
        payload={
            "is_complete": result.status == "complete",
            "missing_fields": result.requirement.missing_fields(),
            "mcp_name": result.requirement.mcp_name,
        },
    )
    publish_event(
        state,
        event_type,
        "requirements_agent",
        "Requirements completed" if result.status == "complete" else "Clarification needed from user",
        payload={
            "message_to_user": result.message_to_user,
            "clarifications_needed": result.requirement.clarifications_needed,
        },
    )

    return {
        **state,
        "messages": list(session.messages) + [AIMessage(content=result.message_to_user)],
        "requirement": result.requirement,
        "agent_prompt": result.message_to_user,
        "phase": "complete" if result.status == "complete" else "gathering",
        "error": None,
    }
