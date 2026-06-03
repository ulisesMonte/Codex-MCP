"""Tests for FastMCP structure guards in the creator agent."""
from agents.mcp_creator_agent import (
    _errors_are_structural,
    _has_fastmcp_structure,
    _render_code,
)
from models.mcp_design import MCPDesign, ToolImplementation
from models.mcp_requirement import MCPRequirement, ToolSpec


def _sample_design() -> MCPDesign:
    req = MCPRequirement(
        mcp_name="microservice_factory",
        description="Factory MCP",
        tools=[
            ToolSpec(
                name="controller_factory",
                description="Generates controller code",
                returns_type="str",
                returns_description="Python source",
            ),
        ],
    )
    return MCPDesign(
        requirement=req,
        server_filename="microservice_factory_server.py",
        imports=[],
        tools=[
            ToolImplementation(
                name="controller_factory",
                signature="specification: str",
                return_type="str",
                description="Generates controller code",
                returns_description="Python source",
                body='    return specification',
            ),
        ],
        resources=[],
    )


def test_render_code_has_fastmcp_structure():
    code = _render_code(_sample_design())
    assert _has_fastmcp_structure(code)
    assert "from fastmcp import FastMCP" in code
    assert "@mcp.tool()" in code
    assert 'if __name__ == "__main__"' in code


def test_has_fastmcp_structure_rejects_arbitrary_python():
    stub = "def calculate_area(radius: float) -> float:\n    return 3.14 * radius ** 2\n"
    assert not _has_fastmcp_structure(stub)


def test_errors_are_structural_detects_missing_fastmcp():
    assert _errors_are_structural(["Missing FastMCP import: 'from fastmcp import FastMCP'"])
    assert not _errors_are_structural(["SyntaxError at line 10: invalid syntax"])
