"""
Validator Agent — deterministic validation of generated MCP server code.

No LLM involved. Uses Python's AST parser + structural checks.
If validation fails, returns errors as feedback for the Creator Agent retry.
Maximum 3 retries before giving up.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from domain.codegen.code_validator import GeneratedCodeValidator, validate_code
from shared.progress import agent_note
from config.constants import MAX_VALIDATION_RETRIES
from events.types import EventTypes
from models.mcp_design import GeneratedMCP
from orchestrator.events import publish_event

if TYPE_CHECKING:
    from orchestrator.state import MCPFactoryState

MAX_RETRIES = MAX_VALIDATION_RETRIES

_code_validator = GeneratedCodeValidator()


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

    errors = _code_validator.validate(generated.code, generated.design.requirement.dependencies).errors

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
    """Backward-compatible wrapper for tests."""
    return validate_code(code, dependencies)


def _validate_no_stubs(code: str) -> list[str]:
    return _code_validator._validate_no_stubs(code)
