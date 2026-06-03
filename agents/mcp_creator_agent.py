"""
MCP Creator Agent — generates the final Python source code for the MCP server.

Uses Jinja2 templates + the Coder LLM to produce a complete, runnable
FastMCP server file that is written to disk in generated/mcps/.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader
from langchain_core.messages import HumanMessage, SystemMessage

from agents.codegen_router import build_design_from_requirement, get_module_helpers
from cli.agent_console import agent_note
from config.paths import generated_mcps_dir
from context.service import format_context_for_prompt, retrieve_codegen_context
from events.types import EventTypes
from llm.ollama_client import get_coder_llm
from models.mcp_design import GeneratedMCP, MCPDesign
from orchestrator.events import publish_event

if TYPE_CHECKING:
    from orchestrator.state import MCPFactoryState

# Resolve template directory relative to this file
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
GENERATED_DIR = generated_mcps_dir()

_STRUCTURAL_ERROR_MARKERS = (
    "Missing FastMCP",
    "No @mcp.tool",
    "Missing FastMCP instance",
    "Missing entry point",
)


def mcp_creator_agent_node(state: "MCPFactoryState") -> "MCPFactoryState":
    """LangGraph node: renders the MCP server code and writes it to disk."""
    design: MCPDesign = state["design"]
    attempt: int = state.get("validation_attempts", 0)
    prev_errors: list[str] = []

    if attempt > 0 and state.get("generated_mcp"):
        prev_errors = state["generated_mcp"].validation_errors

    agent_note(
        f"Creator — generando {design.server_filename}"
        + (f" (retry {attempt}/{3})" if attempt > 0 else "")
    )

    publish_event(
        state,
        EventTypes.CODE_GENERATION_STARTED,
        "mcp_creator_agent",
        "Generating MCP server code",
        payload={"attempt": attempt, "server_filename": design.server_filename},
    )

    try:
        active_design = design
        code = _render_code(active_design, prev_errors)

        if prev_errors:
            stub_errors = any(
                "stub" in e.lower() or "specification" in e.lower() or "todo" in e.lower()
                for e in prev_errors
            )
            if stub_errors:
                agent_note("Reconstruyendo design determinístico (implementación débil)")
                active_design = build_design_from_requirement(design.requirement)
                code = _render_code(active_design, [])
            elif _errors_are_structural(prev_errors):
                agent_note("Re-render desde plantilla FastMCP (errores estructurales)")
                code = _render_code(active_design, [])
            else:
                publish_event(
                    state,
                    EventTypes.CODE_REPAIR_STARTED,
                    "mcp_creator_agent",
                    "Repairing generated code from validator feedback",
                    payload={"attempt": attempt, "errors": prev_errors},
                )
                repaired = _repair_code_with_llm(active_design, code, prev_errors)
                if _has_fastmcp_structure(repaired):
                    code = repaired
                else:
                    agent_note("Reparación LLM perdió estructura FastMCP — plantilla original")
                    code = _render_code(active_design, [])

        server_path = _write_to_disk(active_design.server_filename, code)

        generated = GeneratedMCP(
            design=active_design,
            code=code,
            server_path=str(server_path),
            status="generated",
            validation_passed=False,
        )

        agent_note(f"Código escrito → {server_path.name}")
        publish_event(
            state,
            EventTypes.CODE_GENERATED,
            "mcp_creator_agent",
            "MCP server code generated",
            payload={"server_path": str(server_path), "code_lines": len(code.splitlines())},
        )
        return {**state, "generated_mcp": generated, "design": active_design, "error": None}

    except Exception as e:
        agent_note(f"Creator falló: {e}")
        publish_event(
            state,
            EventTypes.CODE_GENERATION_FAILED,
            "mcp_creator_agent",
            "Code generation failed",
            level="error",
            payload={"error": str(e), "server_filename": design.server_filename},
        )
        return {**state, "error": str(e)}


def _errors_are_structural(errors: list[str]) -> bool:
    """True when validator reported missing FastMCP shell, not implementation details."""
    return any(
        any(marker in err for marker in _STRUCTURAL_ERROR_MARKERS)
        for err in errors
    )


def _has_fastmcp_structure(code: str) -> bool:
    """Minimal guard: output must look like a FastMCP server, not arbitrary Python."""
    if "from fastmcp import FastMCP" not in code and "import fastmcp" not in code:
        return False
    if "FastMCP(" not in code:
        return False
    has_tool = "@mcp.tool()" in code
    has_resource = bool(re.search(r"@mcp\.resource\(", code))
    if not has_tool and not has_resource:
        return False
    if '__name__ == "__main__"' not in code and "__name__ == '__main__'" not in code:
        return False
    return True


def _render_code(design: MCPDesign, prev_errors: list[str] | None = None) -> str:
    """Render the Jinja2 template for the appropriate transport."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    transport = design.requirement.transport
    template_name = (
        "mcp_server_http.py.j2"
        if transport == "http"
        else "mcp_server_stdio.py.j2"
    )

    template = env.get_template(template_name)

    module_helpers = get_module_helpers(design.requirement)

    return template.render(
        mcp_name=design.requirement.mcp_name,
        description=design.requirement.description,
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        imports=design.imports,
        module_helpers=module_helpers,
        tools=design.tools,
        resources=design.resources,
        port=design.requirement.port,
        dependencies=design.requirement.dependencies,
        prev_errors=prev_errors or [],
    )


def _repair_code_with_llm(design: MCPDesign, code: str, errors: list[str]) -> str:
    """
    Ask the coder model to repair generated code after deterministic validation fails.
    Caller must verify FastMCP structure before accepting the result.
    """
    agent_note("Enviando feedback del validador al coder model…")

    system_prompt = """You repair Python FastMCP server code.
Return only the complete corrected Python source code.
Do not include markdown, explanations, diffs, or comments about the repair.
You MUST keep: from fastmcp import FastMCP, mcp = FastMCP(...), @mcp.tool() decorators,
and if __name__ == "__main__": mcp.run().
Keep the same MCP tools, resources, transport, and public signatures unless fixing syntax requires otherwise."""

    prompt = (
        "The generated MCP server failed validation.\n\n"
        f"Requirement:\n{design.requirement.model_dump_json(indent=2)}\n\n"
        f"Design:\n{design.model_dump_json(indent=2)}\n\n"
        f"Validation errors:\n{errors}\n\n"
        f"Current code:\n```python\n{code}\n```\n\n"
    )
    rag = format_context_for_prompt(
        retrieve_codegen_context(
            f"{design.requirement.mcp_name} fastmcp {' '.join(t.name for t in design.tools)}",
            dependencies=design.requirement.dependencies,
            limit=6,
        )
    )
    if rag:
        prompt += f"{rag}\n\n"
    prompt += (
        "Return the full corrected Python file with real implementations "
        "(no placeholder success strings). Preserve the FastMCP server structure."
    )

    try:
        llm = get_coder_llm(temperature=0.02, quiet=True)
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt),
        ])
        repaired = _extract_python_code(response.content)
        if repaired.strip():
            return repaired
    except Exception as e:
        agent_note(f"Reparación LLM falló, manteniendo plantilla: {e}")

    return code


def _extract_python_code(text: str) -> str:
    """Extract a full Python source response, accepting fenced or raw code."""
    raw = text.strip()
    fenced = re.search(r"```(?:python|py)?\s*([\s\S]*?)\s*```", raw)
    if fenced:
        return fenced.group(1).strip() + "\n"
    return raw + ("\n" if raw else "")


def _write_to_disk(filename: str, code: str) -> Path:
    """Write generated code to the generated/mcps directory."""
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    path = GENERATED_DIR / filename
    path.write_text(code, encoding="utf-8")
    return path
