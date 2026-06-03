"""
Tests for MCPRequirement model — checklist and validation logic.
"""
import pytest
from models.mcp_requirement import (
    MCPRequirement,
    ToolSpec,
    ResourceSpec,
    ParameterSpec,
    OutputMode,
)


class TestMCPRequirementChecklist:
    def test_empty_requirement_is_not_ready(self):
        req = MCPRequirement()
        assert not req.is_ready()

    def test_missing_name(self):
        req = MCPRequirement(
            description="A test MCP",
            tools=[ToolSpec(name="foo", description="bar", returns_type="str", returns_description="result")],
        )
        assert "mcp_name" in req.missing_fields()

    def test_missing_tools_and_resources(self):
        req = MCPRequirement(mcp_name="test", description="desc")
        assert "has_tools_or_resources" in req.missing_fields()

    def test_complete_with_tool(self):
        req = MCPRequirement(
            mcp_name="price_checker",
            description="Checks product prices",
            tools=[
                ToolSpec(
                    name="get_price",
                    description="Returns price of a product",
                    parameters=[
                        ParameterSpec(name="product_id", type="str", description="Product ID")
                    ],
                    returns_type="float",
                    returns_description="Price in USD",
                )
            ],
            output_mode=OutputMode.CODE_ONLY,
        )
        assert req.is_ready(), f"Missing: {req.missing_fields()}"

    def test_complete_with_resource_only(self):
        req = MCPRequirement(
            mcp_name="catalog",
            description="Product catalog resource",
            resources=[
                ResourceSpec(
                    uri_template="data://products/{id}",
                    name="get_product",
                    description="Returns product data",
                )
            ],
            output_mode=OutputMode.CODE_ONLY,
        )
        assert req.is_ready(), f"Missing: {req.missing_fields()}"


class TestOutputMode:
    def test_default_output_mode(self):
        req = MCPRequirement()
        assert req.output_mode == OutputMode.CODE_ONLY

    def test_output_mode_values(self):
        assert OutputMode.CODE_ONLY.value == "code_only"
        assert OutputMode.DEPLOY_LOCAL.value == "deploy_local"
        assert OutputMode.DEPLOY_HTTP.value == "deploy_http"

    def test_set_output_mode(self):
        req = MCPRequirement(
            mcp_name="test",
            description="test",
            output_mode=OutputMode.DEPLOY_HTTP,
            port=9000,
        )
        assert req.output_mode == OutputMode.DEPLOY_HTTP
        assert req.port == 9000


class TestToolSpec:
    def test_tool_with_optional_param(self):
        tool = ToolSpec(
            name="search",
            description="Search items",
            parameters=[
                ParameterSpec(name="query", type="str", description="Search query"),
                ParameterSpec(name="limit", type="int", description="Max results", required=False, default=10),
            ],
            returns_type="list[dict]",
            returns_description="List of matching items",
        )
        assert len(tool.parameters) == 2
        assert tool.parameters[1].required is False
        assert tool.parameters[1].default == 10
