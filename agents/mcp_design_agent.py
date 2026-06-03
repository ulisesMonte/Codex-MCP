"""
MCP Design Agent — converts MCPRequirement into MCPDesign.

Always builds a deterministic domain-aware baseline, then optionally merges
stronger tool bodies from the coder LLM (never accepts stubs over baseline).
"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from agents.codegen_router import (
    build_design_from_requirement,
    is_weak_tool_implementation,
    merge_designs,
)
from cli.agent_console import agent_note
from context.service import (
    format_context_for_prompt,
    get_similar_implementation,
    retrieve_codegen_context,
)
from events.types import EventTypes
from llm.ollama_client import get_coder_llm
from models.mcp_design import MCPDesign, ResourceImplementation, ToolImplementation
from models.mcp_requirement import MCPRequirement, ParameterSpec
from orchestrator.events import publish_event

if TYPE_CHECKING:
    from orchestrator.state import MCPFactoryState

SYSTEM_PROMPT = """You are an expert Python FastMCP developer.
Given an MCP requirement, output JSON with real tool implementations.

{
  "server_filename": "name_server.py",
  "imports": ["import os"],
  "tools": [{
    "name": "tool_name",
    "signature": "param: str",
    "return_type": "str",
    "description": "...",
    "returns_description": "...",
    "body": "    x = param.upper()\\n    return x"
  }],
  "resources": [],
  "has_external_calls": false,
  "estimated_complexity": "simple"
}

RULES:
- body: real Python, 4-space indent, use \\n between lines
- NEVER TODO, stub, "Not implemented", or return f"Executed ..."
- Use os.getenv() for secrets; never hardcode credentials
- Factory tools: specification: str → return complete generated source code
- BigQuery: google.cloud.bigquery + GOOGLE_APPLICATION_CREDENTIALS
- DB tools: use DATABASE_URL env var
"""


def mcp_design_agent_node(state: "MCPFactoryState") -> "MCPFactoryState":
    req: MCPRequirement = state["requirement"]
    agent_note(f"Design agent — diseñando {req.mcp_name} ({len(req.tools)} tools)…")

    publish_event(
        state,
        EventTypes.DESIGN_STARTED,
        "mcp_design_agent",
        "Resolving technical MCP design",
        payload={"mcp_name": req.mcp_name},
    )

    baseline = build_design_from_requirement(req)
    design = baseline
    llm_used = False

    try:
        llm_design = _try_llm_design(req, state)
        if llm_design is not None:
            design = merge_designs(baseline, llm_design)
            llm_used = True
    except Exception as e:
        agent_note(f"LLM design skipped — usando baseline determinístico: {e}")

    agent_note(
        f"Design listo: {len(design.tools)} tools"
        + (" (baseline + LLM merge)" if llm_used else " (determinístico)")
    )
    publish_event(
        state,
        EventTypes.DESIGN_COMPLETED,
        "mcp_design_agent",
        "Technical design completed",
        payload={
            "server_filename": design.server_filename,
            "tools": len(design.tools),
            "deterministic_baseline": True,
            "llm_merged": llm_used,
        },
    )
    return {**state, "design": design, "error": None}


def _try_llm_design(req: MCPRequirement, state: "MCPFactoryState") -> MCPDesign | None:
    llm = get_coder_llm(temperature=0.05, quiet=True)
    query = f"{req.mcp_name} {' '.join(t.name for t in req.tools)} {req.description}"
    rag_chunks = retrieve_codegen_context(query, dependencies=req.dependencies, limit=8)
    if not rag_chunks:
        rag_chunks = get_similar_implementation(req.mcp_name, [t.name for t in req.tools], limit=5)
    rag_block = format_context_for_prompt(rag_chunks)

    validated = state.get("validated_research") or {}
    scout_block = validated.get("context_markdown", "")
    if scout_block:
        rag_block = f"{scout_block}\n\n{rag_block}" if rag_block else scout_block

    hints = []
    for t in req.tools:
        if t.implementation_hint:
            hints.append(f"- {t.name}: {t.implementation_hint}")
    hint_block = "\n".join(hints)

    prompt = f"Design MCP server:\n\n{req.model_dump_json(indent=2)}\n\n"
    if hint_block:
        prompt += f"Implementation hints (mandatory):\n{hint_block}\n\n"
    if rag_block:
        prompt += f"{rag_block}\n\n"
    prompt += "JSON only. Real implementations — no stubs."

    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])
    data = _extract_json(response.content.strip())
    return _build_design(req, data)


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for pattern in [r"```json\s*([\s\S]*?)\s*```", r"```\s*([\s\S]*?)\s*```"]:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"No valid JSON in design response: {text[:400]}")


def _build_design(req: MCPRequirement, data: dict) -> MCPDesign:
    tools = [
        ToolImplementation(
            name=t.get("name", ""),
            signature=t.get("signature", ""),
            return_type=t.get("return_type", "str"),
            description=t.get("description", ""),
            returns_description=t.get("returns_description", ""),
            body=_normalize_body(t.get("body", "")),
        )
        for t in data.get("tools", [])
        if t.get("name") and not is_weak_tool_implementation(
            ToolImplementation(
                name=t.get("name", ""),
                signature=t.get("signature", ""),
                return_type="str",
                description="",
                returns_description="",
                body=_normalize_body(t.get("body", "")),
            )
        )
    ]
    if not tools:
        return build_design_from_requirement(req)

    resources = [
        ResourceImplementation(
            uri_template=r.get("uri_template", ""),
            name=r.get("name", ""),
            params_signature=r.get("params_signature", ""),
            return_type=r.get("return_type", "str"),
            description=r.get("description", ""),
            body=_normalize_body(r.get("body", '    return "ok"')),
        )
        for r in data.get("resources", [])
    ]
    return MCPDesign(
        requirement=req,
        server_filename=data.get("server_filename", f"{req.mcp_name}_server.py"),
        imports=data.get("imports", []),
        tools=tools,
        resources=resources,
        has_external_calls=data.get("has_external_calls", False),
        estimated_complexity=data.get("estimated_complexity", "simple"),
    )


def _normalize_body(body: str) -> str:
    if not body:
        return ""
    body = body.replace("\\n", "\n").replace("\\t", "\t")
    lines = body.splitlines()
    normalized: list[str] = []
    for line in lines:
        s = line.rstrip()
        if s and not s.startswith((" ", "\t")):
            normalized.append(f"    {s}")
        else:
            normalized.append(s)
    return "\n".join(normalized)
