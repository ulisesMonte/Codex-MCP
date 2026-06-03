"""
Tests for the Validator Agent — no LLM required, purely deterministic.
"""
import pytest
from agents.validator_agent import _validate


# ── Valid code samples ────────────────────────────────────────────────────

VALID_STDIO = '''
from fastmcp import FastMCP

mcp = FastMCP("test_server", description="Test")

@mcp.tool()
def say_hello(name: str) -> str:
    """Says hello."""
    return f"Hello, {name}!"

if __name__ == "__main__":
    mcp.run()
'''

VALID_HTTP = '''
from fastmcp import FastMCP

mcp = FastMCP("http_server")

@mcp.tool()
def ping() -> str:
    """Ping the server."""
    return "pong"

@mcp.resource("data://info")
def get_info() -> str:
    """Returns server info."""
    return "MCP HTTP Server"

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
'''

VALID_WITH_RESOURCE_ONLY = '''
from fastmcp import FastMCP

mcp = FastMCP("resource_server")

@mcp.resource("data://items/{item_id}")
def get_item(item_id: str) -> str:
    """Returns item data."""
    return f"Item: {item_id}"

if __name__ == "__main__":
    mcp.run()
'''

# ── Invalid code samples ──────────────────────────────────────────────────

MISSING_FASTMCP_IMPORT = '''
mcp = SomeThing("broken")

@mcp.tool()
def foo() -> str:
    return "bar"

if __name__ == "__main__":
    mcp.run()
'''

MISSING_DECORATOR = '''
from fastmcp import FastMCP
mcp = FastMCP("no_tools")

def orphan_function() -> str:
    return "no decorator"

if __name__ == "__main__":
    mcp.run()
'''

MISSING_ENTRYPOINT = '''
from fastmcp import FastMCP
mcp = FastMCP("no_main")

@mcp.tool()
def foo() -> str:
    return "bar"
'''

SYNTAX_ERROR = '''
from fastmcp import FastMCP
mcp = FastMCP("broken"

@mcp.tool()
def foo( -> str:
    return "oops"
'''


# ── Tests ─────────────────────────────────────────────────────────────────

class TestValidatorPass:
    def test_valid_stdio_server(self):
        errors = _validate(VALID_STDIO, [])
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_valid_http_server(self):
        errors = _validate(VALID_HTTP, [])
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_valid_resource_only(self):
        errors = _validate(VALID_WITH_RESOURCE_ONLY, [])
        assert errors == [], f"Expected no errors, got: {errors}"


class TestValidatorFail:
    def test_missing_fastmcp_import(self):
        errors = _validate(MISSING_FASTMCP_IMPORT, [])
        assert any("FastMCP" in e for e in errors), f"Expected FastMCP import error, got: {errors}"

    def test_missing_decorator(self):
        errors = _validate(MISSING_DECORATOR, [])
        assert any("decorator" in e.lower() for e in errors), f"Expected decorator error, got: {errors}"

    def test_missing_entrypoint(self):
        errors = _validate(MISSING_ENTRYPOINT, [])
        assert any("__main__" in e or "entry" in e.lower() for e in errors)

    def test_syntax_error_caught(self):
        errors = _validate(SYNTAX_ERROR, [])
        assert any("SyntaxError" in e for e in errors), f"Expected SyntaxError, got: {errors}"

    def test_syntax_error_stops_further_checks(self):
        """When there's a syntax error, only that error is returned."""
        errors = _validate(SYNTAX_ERROR, [])
        # Should have exactly 1 error (syntax) — no further checks run
        assert len(errors) == 1


class TestValidatorDependencies:
    def test_missing_dep_does_not_block_valid_code(self):
        errors = _validate(VALID_STDIO, ["nonexistent_package_xyz"])
        assert errors == [], f"Deps must not block: {errors}"

    def test_google_cloud_bigquery_dep_does_not_block(self):
        errors = _validate(VALID_STDIO, ["google-cloud-bigquery"])
        assert errors == [], f"google-cloud-bigquery must not block: {errors}"
