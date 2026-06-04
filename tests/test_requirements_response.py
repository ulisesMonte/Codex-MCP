import json

from requirements.response import (
    build_clarification_message,
    parse_requirements_response,
)
from models.mcp_requirement import MCPRequirement


def test_parse_empty_message_uses_fallback_not_json():
    raw = json.dumps({
        "status": "gathering",
        "message_to_user": "",
        "current_requirement": {
            "mcp_name": "bq_tools",
            "description": "BigQuery reader",
            "clarifications_needed": ["Definir dataset y tabla"],
        },
    })
    msg, status, _, ok = parse_requirements_response(raw, None)
    assert ok
    assert status == "gathering"
    assert "bq_tools" in msg or "dataset" in msg.lower() or "Definir" in msg
    assert not msg.strip().startswith("{")


def test_parse_failure_still_returns_questions():
    raw = '**Requisitos recopilados hasta ahora:**\n{"status": "gathering", "message_to_user": ""'
    msg, status, _, _ = parse_requirements_response(raw, None)
    assert status == "gathering"
    assert len(msg) > 20
    assert "{" not in msg[:5]


def test_build_clarification_lists_missing_fields():
    req = MCPRequirement(mcp_name="", description="")
    msg = build_clarification_message(req)
    assert "confirm" not in msg.lower() or "MCP" in msg
