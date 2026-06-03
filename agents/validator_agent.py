"""
Validator Agent — deterministic validation of generated MCP server code.

No LLM involved. Uses Python's AST parser + structural checks.
If validation fails, returns errors as feedback for the Creator Agent retry.
Maximum 3 retries before giving up.
"""
from __future__ import annotations

import ast
import importlib.util
import re
from typing import TYPE_CHECKING

from cli.agent_console import agent_note
from events.types import EventTypes
from models.mcp_design import GeneratedMCP
from orchestrator.events import publish_event

if TYPE_CHECKING:
    from orchestrator.state import MCPFactoryState

MAX_RETRIES = int(__import__("os").getenv("MAX_VALIDATION_RETRIES", "3"))


def validator_agent_node(state: "MCPFactoryState") -> "MCPFactoryState":
    """LangGraph node: validates the generated MCP code deterministically."""
    generated: GeneratedMCP = state["generated_mcp"]
    attempts: int = state.get("validation_attempts", 0) + 1

    agent_note(f"Validator — revisando código (intento {attempts}/{MAX_RETRIES})…")

    publish_event(
        state,
        EventTypes.VALIDATION_STARTED,
        "validator_agent",
        "Validating generated MCP code",
        payload={"attempt": attempts, "server_path": generated.server_path},
    )

    errors = _validate(generated.code, generated.design.requirement.dependencies)

    if errors:
        agent_note(f"{len(errors)} issue(s) — reintento programado")
        for e in errors:
            agent_note(f"  • {e}")

        generated = generated.model_copy(update={
            "validation_passed": False,
            "validation_errors": errors,
        })
        publish_event(
            state,
            EventTypes.VALIDATION_FAILED,
            "validator_agent",
            "Generated MCP code failed validation",
            level="warning",
            payload={"attempt": attempts, "errors": errors},
        )
        if attempts < MAX_RETRIES:
            publish_event(
                state,
                EventTypes.VALIDATION_RETRY_SCHEDULED,
                "validator_agent",
                "Scheduling code generation retry",
                level="warning",
                payload={"attempt": attempts, "max_retries": MAX_RETRIES},
            )
        error_msg = None
        if attempts >= MAX_RETRIES:
            error_msg = "Validation failed after retries:\n" + "\n".join(f"• {e}" for e in errors)
        return {
            **state,
            "generated_mcp": generated,
            "validation_attempts": attempts,
            "error": error_msg,
        }

    agent_note("Validación OK — código sintácticamente correcto")
    generated = generated.model_copy(update={
        "validation_passed": True,
        "validation_errors": [],
        "status": "generated",
    })
    publish_event(
        state,
        EventTypes.VALIDATION_PASSED,
        "validator_agent",
        "Generated MCP code passed validation",
        payload={"attempt": attempts, "server_path": generated.server_path},
    )
    return {
        **state,
        "generated_mcp": generated,
        "validation_attempts": attempts,
    }


def _validate(code: str, dependencies: list[str]) -> list[str]:
    """Run blocking validation checks. Returns errors (empty = pass).

    Missing pip dependencies are NOT blocking — the generated MCP may use
    packages not installed in the factory venv (e.g. google-cloud-bigquery).
    """
    errors: list[str] = []

    try:
        ast.parse(code)
    except SyntaxError as e:
        errors.append(f"SyntaxError at line {e.lineno}: {e.msg}")
        return errors

    if "from fastmcp import FastMCP" not in code and "import fastmcp" not in code:
        errors.append("Missing FastMCP import: 'from fastmcp import FastMCP'")

    has_tool = "@mcp.tool()" in code
    has_resource = bool(re.search(r'@mcp\.resource\(', code))
    if not has_tool and not has_resource:
        errors.append("No @mcp.tool() or @mcp.resource() decorators found")

    if "FastMCP(" not in code:
        errors.append("Missing FastMCP instance: mcp = FastMCP(...)")

    if 'if __name__ == "__main__"' not in code and "if __name__ == '__main__'" not in code:
        errors.append("Missing entry point: if __name__ == '__main__': mcp.run()")

    errors.extend(_validate_no_stubs(code))

    _log_dependency_notes(dependencies)
    return errors


_STUB_BODY_RE = re.compile(
    r"(?:#\s*)?TODO:\s*implement|return\s+[\"']stub[\"']|not implemented|"
    r"return f[\"']Executed|^\s*#\s*Implementation\s*$|"
    r'result\s*=\s*\{\s*["\'](?:payload|query|id)["\']\s*:\s*\w+\s*\}',
    re.I | re.M,
)


def _validate_no_stubs(code: str) -> list[str]:
    """Reject placeholder factory implementations that passed structural checks."""
    errors: list[str] = []
    if _STUB_BODY_RE.search(code):
        errors.append("Tool bodies contain TODO/stub placeholders — need real implementations")
    if "_factory" in code:
        for match in re.finditer(r"def\s+(\w+_factory)\(([^)]*)\)", code):
            name, params = match.group(1), match.group(2)
            if "specification" not in params:
                errors.append(
                    f"Factory tool `{name}` must accept specification: str (got: {params or 'no params'})"
                )
        if "def _parse_microservice_spec" not in code and "def _emit_repository" not in code:
            if re.search(r"_factory", code) and _STUB_BODY_RE.search(code):
                errors.append("Microservice factory missing NL parsing helpers")
    if re.search(r"\\n\s+return", code):
        errors.append("Tool body contains literal \\n instead of real newlines")
    return errors


def _log_dependency_notes(dependencies: list[str]) -> None:
    """Informative only — does not block validation."""
    for dep in dependencies:
        module = _pip_name_to_import(dep)
        try:
            missing = importlib.util.find_spec(module) is None
        except (ModuleNotFoundError, ValueError, ImportError):
            missing = True
        if missing:
            agent_note(
                f"Dependencia '{dep}' no instalada aquí "
                f"(OK — pip install {dep} en el entorno destino)"
            )


def _pip_name_to_import(dep: str) -> str:
    """Map pip package name to Python import path for find_spec."""
    name = dep.strip().split("[")[0].split("==")[0].strip()
    if name.startswith("google-cloud-"):
        suffix = name.removeprefix("google-cloud-").replace("-", "_")
        return f"google.cloud.{suffix}"
    return name.replace("-", "_").split(".")[0]
