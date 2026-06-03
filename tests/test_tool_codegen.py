"""Tests for generic domain-aware codegen (all requirement types)."""
import ast

from agents.codegen_router import build_design_from_requirement, is_weak_tool_implementation
from agents.mcp_creator_agent import _render_code
from agents.validator_agent import _validate
from models.mcp_requirement import MCPRequirement, ParameterSpec, ToolSpec


def test_bigquery_design_has_real_client_code():
    req = MCPRequirement(
        mcp_name="source_connection",
        description="Consulta la tabla info.source en BigQuery proyecto test",
        tools=[
            ToolSpec(
                name="source_connection",
                description="Query BigQuery table info.source",
                returns_type="str",
                returns_description="JSON rows",
                implementation_hint="BigQuery via GOOGLE_APPLICATION_CREDENTIALS",
            )
        ],
        dependencies=["google-cloud-bigquery"],
    )
    design = build_design_from_requirement(req)
    code = _render_code(design)
    ast.parse(code)
    assert "bigquery.Client" in code
    assert "GOOGLE_APPLICATION_CREDENTIALS" in code
    assert "TODO" not in code
    assert _validate(code, req.dependencies) == []


def test_postgres_connection_design():
    req = MCPRequirement(
        mcp_name="connection_manager",
        description="MCP para crear conexiones a postgres",
        tools=[
            ToolSpec(
                name="create_connection",
                description="Validate postgres connection",
                returns_type="str",
                returns_description="Connection status JSON",
            )
        ],
        dependencies=["psycopg2-binary"],
    )
    design = build_design_from_requirement(req)
    code = _render_code(design)
    assert "psycopg2" in code
    assert "DATABASE_URL" in code
    assert not is_weak_tool_implementation(design.tools[0])


def test_plsql_factory_from_specification():
    req = MCPRequirement(
        mcp_name="plsql_factory",
        description="Genera código PL/SQL desde lenguaje natural",
        tools=[
            ToolSpec(
                name="plsql_generator",
                description="Genera PL/SQL",
                returns_type="str",
                returns_description="PL/SQL source",
            )
        ],
    )
    design = build_design_from_requirement(req)
    tool = design.tools[0]
    assert "specification" in tool.signature
    assert "CREATE OR REPLACE PROCEDURE" in tool.body or "re.search" in tool.body


def test_generic_tool_with_params():
    req = MCPRequirement(
        mcp_name="echo_tools",
        description="Echo MCP",
        tools=[
            ToolSpec(
                name="echo_message",
                description="Echo input",
                parameters=[
                    ParameterSpec(name="message", type="str", description="text"),
                ],
                returns_type="str",
                returns_description="echo",
            )
        ],
    )
    design = build_design_from_requirement(req)
    assert "message" in design.tools[0].body
    assert not is_weak_tool_implementation(design.tools[0])
