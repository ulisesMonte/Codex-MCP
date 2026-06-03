"""Tests for general code generation quality across requirement types."""
import ast

from agents.codegen_router import build_design_from_requirement, get_module_helpers, is_weak_tool_implementation
from agents.mcp_creator_agent import _render_code
from agents.requirement_intent import GenerationIntent, infer_generation_intent
from agents.requirements_enrichment import enrich_requirement, finalize_requirement
from agents.validator_agent import _validate
from langchain_core.messages import HumanMessage
from models.mcp_requirement import MCPRequirement, ToolSpec


DAO_USER_TEXT = (
    "quiero que crees un mcp que sirva para crear un DAO, osea que ayude a un agente "
    "a crear Daos a partir de mcp y cada tool del mcp debe ser una operacion CRUD del dao"
)


def test_dao_intent_is_code_generator():
    req = enrich_requirement(MCPRequirement(), DAO_USER_TEXT)
    assert req.generation_intent == GenerationIntent.CODE_GENERATOR
    assert len(req.tools) == 4
    assert all(t.parameters[0].name == "specification" for t in req.tools)


def test_dao_codegen_produces_real_python_not_echo():
    req = finalize_requirement(
        enrich_requirement(MCPRequirement(), DAO_USER_TEXT),
        [HumanMessage(content=DAO_USER_TEXT)],
    )
    design = build_design_from_requirement(req)
    code = _render_code(design)
    ast.parse(code)

    assert "_parse_nl_spec" in code
    assert "_emit_crud_method" in code
    assert "def create(specification: str)" in code
    assert 'result = {"payload": payload}' not in code
    assert not any(is_weak_tool_implementation(t) for t in design.tools)

    errors = _validate(code, req.dependencies)
    assert errors == [], errors


def test_runtime_crud_has_shared_store():
    req = MCPRequirement(
        mcp_name="records_mcp",
        description="Perform CRUD operations on records at runtime",
        generation_intent=GenerationIntent.RUNTIME,
        tools=[
            ToolSpec(name="create", description="Create record", returns_type="str", returns_description="r"),
            ToolSpec(name="read", description="Read records", returns_type="str", returns_description="r"),
        ],
    )
    design = build_design_from_requirement(req)
    code = _render_code(design)
    assert "_runtime_store" in code
    assert "store[new_id] = data" in code


def test_code_generator_helpers_injected():
    req = enrich_requirement(MCPRequirement(), DAO_USER_TEXT)
    helpers = get_module_helpers(req)
    assert "_parse_nl_spec" in helpers
    assert "_emit_crud_method" in helpers


def test_infer_intent_integration_vs_codegen():
    bq = infer_generation_intent(
        "tool que se conecta a bigquery proyecto test dataset info tabla source",
        MCPRequirement(description="Query BigQuery"),
    )
    assert bq == GenerationIntent.INTEGRATION

    gen = infer_generation_intent(DAO_USER_TEXT, MCPRequirement())
    assert gen == GenerationIntent.CODE_GENERATOR
