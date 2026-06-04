"""Tests for domain layer (OOP models)."""
from domain.codegen.code_validator import GeneratedCodeValidator
from domain.requirements.conversation import ConversationSignals, RequirementLifecycle
from domain.requirements.intent_resolver import GenerationIntentResolver
from domain.requirements.merger import RequirementMerger
from domain.session import MCPFactorySession
from models.mcp_requirement import GenerationIntent, MCPRequirement, ToolSpec


def test_requirement_merger_builds_from_dict():
    merger = RequirementMerger()
    req = merger.merge({"mcp_name": "test_tools", "description": "Test", "tools": []}, None)
    assert req.mcp_name == "test_tools"


def test_intent_resolver_detects_code_generator():
    resolver = GenerationIntentResolver()
    req = MCPRequirement(
        mcp_name="factory_mcp",
        description="Generate DAO code from natural language",
        tools=[ToolSpec(name="dao_factory", description="Generates DAO", returns_type="str")],
    )
    assert resolver.infer("generar código desde lenguaje natural", req) == GenerationIntent.CODE_GENERATOR


def test_conversation_signals_confirm():
    signals = ConversationSignals()
    assert signals.user_confirmed("confirm")
    assert signals.is_affirmative("sí")
    assert not signals.user_rejects_proposal("confirm")


def test_lifecycle_decide_status_waits_for_confirm():
    lifecycle = RequirementLifecycle()
    req = MCPRequirement(
        mcp_name="bq_tools",
        description="BigQuery reader",
        tools=[ToolSpec(name="query", description="Run query", returns_type="str")],
    )
    status = lifecycle.decide_status(req, "gathering", "sí", [])
    assert status == "gathering"


def test_code_validator_rejects_non_fastmcp():
    validator = GeneratedCodeValidator()
    result = validator.validate("def foo(): pass", [])
    assert not result.passed
    assert any("FastMCP" in e for e in result.errors)


def test_mcp_factory_session_reads_requirement():
    req = MCPRequirement(mcp_name="x", description="y")
    session = MCPFactorySession({"requirement": req, "phase": "gathering"})
    assert session.requirement is req
    assert session.phase == "gathering"
