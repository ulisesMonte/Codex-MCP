"""
Context MCP — exposes code-knowledge search as MCP tools (RAG API).

Run standalone:
  python context/context_mcp_server.py

Factory agents call the same logic internally via context.service.
"""
from __future__ import annotations

import json

from fastmcp import FastMCP

from context.service import (
    format_context_for_prompt,
    get_similar_implementation,
    search_generated_mcps,
    search_knowledge,
)

mcp = FastMCP(
    "code_context",
    description="Search technical knowledge, generated MCPs, and patterns for code generation",
)


@mcp.tool()
def search_code_knowledge(query: str, limit: int = 5) -> str:
    """Search built-in technical docs (FastMCP, microservices, connections)."""
    chunks = search_knowledge(query, limit=max(1, min(limit, 10)))
    return format_context_for_prompt(chunks) or "No knowledge matches found."


@mcp.tool()
def search_past_mcps(query: str, limit: int = 3) -> str:
    """Search previously generated MCP server source files."""
    chunks = search_generated_mcps(query, limit=max(1, min(limit, 10)))
    return format_context_for_prompt(chunks) or "No generated MCP matches found."


@mcp.tool()
def get_implementation_examples(mcp_name: str, tool_names: str = "") -> str:
    """Retrieve similar implementations for an MCP name and comma-separated tool names."""
    tools = [t.strip() for t in tool_names.split(",") if t.strip()]
    chunks = get_similar_implementation(mcp_name, tools, limit=5)
    payload = [
        {"source": c.source, "title": c.title, "score": c.score, "preview": c.content[:1200]}
        for c in chunks
    ]
    return json.dumps(payload, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
