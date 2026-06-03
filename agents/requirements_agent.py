"""
Requirements Agent — inference-first gathering; user confirms, agents fill details.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.requirements_enrichment import (
    build_confirmation_message,
    combined_user_text,
    decide_status,
    enrich_requirement,
    finalize_requirement,
    is_affirmative,
    user_accepts_proposal,
    user_confirmed,
    user_rejects_proposal,
    user_sent_tool_correction,
)
from agents.requirements_normalize import normalize_clarifications
from agents.requirements_response import parse_requirements_response
from cli.agent_console import agent_note
from events.types import EventTypes
from llm.ollama_client import get_orchestrator_llm
from llm.stream_invoke import invoke_llm_with_progress
from models.mcp_requirement import (
    MCPRequirement,
    OutputMode,
    ParameterSpec,
    ResourceSpec,
    ToolSpec,
    GenerationIntent,
)
from orchestrator.events import publish_event

if TYPE_CHECKING:
    from orchestrator.state import MCPFactoryState


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
    publish_event(
        state,
        EventTypes.REQUIREMENTS_STARTED,
        "requirements_agent",
        "Analyzing user requirements",
    )
    llm = get_orchestrator_llm(temperature=0.1, quiet=True)
    messages = state["messages"]
    current_req: MCPRequirement | None = state.get("requirement")
    user_text = combined_user_text(messages)
    last_user = ""
    for m in reversed(messages):
        if isinstance(m, HumanMessage) and m.content:
            last_user = str(m.content).strip()
            break

    llm_messages: list = [SystemMessage(content=SYSTEM_PROMPT)]
    if current_req:
        ctx = (
            f"\n[CURRENT REQUIREMENT — merge updates]\n"
            f"{current_req.model_dump_json(indent=2)}\n"
        )
        llm_messages.append(SystemMessage(content=ctx))
    if last_user and user_sent_tool_correction(last_user):
        llm_messages.append(
            SystemMessage(
                content=(
                    "[HINT] The user is CORRECTING tool names/count in their last message. "
                    "Replace current_requirement.tools completely from their correction. "
                    "Do NOT repeat a single-tool summary. Reflect ALL tools they named."
                )
            )
        )
    elif last_user and user_rejects_proposal(last_user):
        llm_messages.append(
            SystemMessage(
                content=(
                    "[HINT] The user REJECTED your last proposal. Read their correction carefully, "
                    "REPLACE current_requirement.tools with exactly what they asked for, "
                    "fix mcp_name/description, clear clarifications_needed, and ask for confirmation again. "
                    "Do NOT set status=complete."
                )
            )
        )
    elif last_user and is_affirmative(last_user):
        llm_messages.append(
            SystemMessage(
                content=(
                    "[HINT] The user's last message is an affirmative short answer (sí/yes/ok). "
                    "Apply it to your previous question or proposal, update current_requirement with the "
                    "tools/names you suggested, clear clarifications_needed, and move toward confirmation "
                    "— do not repeat the question."
                )
            )
        )
    llm_messages.extend(messages)

    raw = invoke_llm_with_progress(llm, llm_messages, label="Requirements agent")

    message_to_user, llm_status, req_data, parse_ok = parse_requirements_response(raw, current_req)
    updated_req = _merge_requirement(req_data, current_req)
    updated_req = enrich_requirement(updated_req, user_text, messages)
    updated_req = finalize_requirement(updated_req, messages)
    status = decide_status(updated_req, llm_status, last_user, messages)

    if updated_req.is_ready():
        message_to_user = build_confirmation_message(updated_req)
    elif not message_to_user or message_to_user.strip().startswith("{"):
        message_to_user = build_confirmation_message(updated_req) if updated_req.tools else message_to_user

    if not parse_ok:
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
        if status == "complete"
        else EventTypes.CLARIFICATION_NEEDED
    )
    publish_event(
        state,
        EventTypes.REQUIREMENT_UPDATED,
        "requirements_agent",
        "Requirement state updated",
        payload={
            "is_complete": status == "complete",
            "missing_fields": updated_req.missing_fields(),
            "mcp_name": updated_req.mcp_name,
        },
    )
    publish_event(
        state,
        event_type,
        "requirements_agent",
        "Requirements completed" if status == "complete" else "Clarification needed from user",
        payload={
            "message_to_user": message_to_user,
            "clarifications_needed": updated_req.clarifications_needed,
        },
    )

    return {
        **state,
        "messages": list(messages) + [AIMessage(content=message_to_user)],
        "requirement": updated_req,
        "agent_prompt": message_to_user,
        "phase": "complete" if status == "complete" else "gathering",
        "error": None,
    }


def _merge_requirement(data: dict, current: MCPRequirement | None) -> MCPRequirement:
    if not data:
        return current or MCPRequirement()

    base = current.model_dump() if current else {}

    def get(key: str, fallback=None):
        val = data.get(key)
        return val if val not in (None, "", [], {}) else base.get(key, fallback)

    raw_tools = data.get("tools") if data.get("tools") else base.get("tools", [])
    tools = []
    for t in raw_tools:
        if isinstance(t, dict):
            params = [
                ParameterSpec(
                    name=p.get("name", ""),
                    type=p.get("type", "str"),
                    description=p.get("description", ""),
                    required=p.get("required", True),
                    default=p.get("default"),
                )
                for p in t.get("parameters", [])
            ]
            tools.append(ToolSpec(
                name=t.get("name", ""),
                description=t.get("description", ""),
                parameters=params,
                returns_type=t.get("returns_type", "str"),
                returns_description=t.get("returns_description", ""),
                implementation_hint=t.get("implementation_hint", ""),
            ))
        elif isinstance(t, ToolSpec):
            tools.append(t)

    raw_res = data.get("resources") or base.get("resources", [])
    resources = []
    for r in raw_res:
        if isinstance(r, dict):
            params = [
                ParameterSpec(
                    name=p.get("name", ""),
                    type=p.get("type", "str"),
                    description=p.get("description", ""),
                    required=p.get("required", True),
                )
                for p in r.get("params", [])
            ]
            resources.append(ResourceSpec(
                uri_template=r.get("uri_template", ""),
                name=r.get("name", ""),
                description=r.get("description", ""),
                returns_type=r.get("returns_type", "str"),
                mime_type=r.get("mime_type", "text/plain"),
                has_params=len(params) > 0,
                params=params,
            ))
        elif isinstance(r, ResourceSpec):
            resources.append(r)

    try:
        output_mode = OutputMode(data.get("output_mode") or base.get("output_mode", "code_only"))
    except ValueError:
        output_mode = OutputMode.CODE_ONLY

    clarifications = normalize_clarifications(
        data.get("clarifications_needed") if data.get("clarifications_needed") is not None
        else base.get("clarifications_needed", [])
    )

    return MCPRequirement(
        mcp_name=get("mcp_name", ""),
        description=get("description", ""),
        tools=tools,
        resources=resources,
        transport=get("transport", "stdio"),
        dependencies=get("dependencies", []),
        output_mode=output_mode,
        port=get("port", 8000),
        generation_intent=_parse_generation_intent(data, base),
        is_complete=data.get("is_complete", False),
        clarifications_needed=clarifications,
    )


def _parse_generation_intent(data: dict, base: dict) -> GenerationIntent:
    raw = data.get("generation_intent") or base.get("generation_intent", "auto")
    try:
        return GenerationIntent(raw)
    except ValueError:
        return GenerationIntent.AUTO
