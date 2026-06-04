"""Tests for deterministic microservice factory code generation."""
import ast

from codegen.factory import (
    build_microservice_factory_design,
    is_microservice_factory_requirement,
)
from codegen.router import build_design_from_requirement
from agents.creator import _render_code
from codegen.router import is_weak_tool_implementation
from agents.validator import _validate
from models.mcp_requirement import MCPRequirement, ParameterSpec, ToolSpec


def _factory_req() -> MCPRequirement:
    return MCPRequirement(
        mcp_name="microservice_factory",
        description="Genera controller, service y repository desde lenguaje natural",
        tools=[
            ToolSpec(
                name="controller_factory",
                description="Generates controller code",
                parameters=[ParameterSpec(name="specification", type="str", description="NL spec")],
                returns_type="str",
                returns_description="Python source",
            ),
            ToolSpec(
                name="service_factory",
                description="Generates service code",
                parameters=[ParameterSpec(name="specification", type="str", description="NL spec")],
                returns_type="str",
                returns_description="Python source",
            ),
            ToolSpec(
                name="repository_factory",
                description="Generates repository code",
                parameters=[ParameterSpec(name="specification", type="str", description="NL spec")],
                returns_type="str",
                returns_description="Python source",
            ),
        ],
    )


def test_is_microservice_factory_requirement():
    assert is_microservice_factory_requirement(_factory_req())


def test_build_factory_design_has_specification_and_real_bodies():
    design = build_microservice_factory_design(_factory_req())
    assert len(design.tools) == 3
    for tool in design.tools:
        assert "specification" in tool.signature
        assert "_parse_microservice_spec" in tool.body
        assert not is_weak_tool_implementation(tool)


def test_rendered_factory_mcp_is_valid_python_without_stubs():
    design = build_microservice_factory_design(_factory_req())
    code = _render_code(design)
    ast.parse(code)
    assert "def controller_factory(specification: str)" in code
    assert "def _parse_microservice_spec" in code
    assert "def _emit_repository" in code
    assert "TODO" not in code
    assert 'return "stub"' not in code
    assert _validate(code, []) == []


def test_normalize_body_decodes_json_newlines():
    from agents.design import _normalize_body

    body = _normalize_body("    line1\\n    line2\\n    return x")
    assert "\n" in body
    assert "\\n" not in body


def test_old_stub_code_fails_validation():
    stub = '''from fastmcp import FastMCP
mcp = FastMCP("x")
@mcp.tool()
def service_factory() -> str:
    """Generates service code"""
    # TODO: implement service_factory\\n    return "stub"
if __name__ == "__main__":
    mcp.run()
'''
    errors = _validate(stub, [])
    assert errors, "expected validation errors"
    lowered = " ".join(errors).lower()
    assert "stub" in lowered or "specification" in lowered or "todo" in lowered, errors
