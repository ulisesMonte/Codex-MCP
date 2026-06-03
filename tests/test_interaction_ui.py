from langchain_core.messages import AIMessage, HumanMessage

from cli.interaction_ui import last_agent_message, pending_items
from models.mcp_requirement import MCPRequirement, ToolSpec


def test_last_agent_message_returns_latest_ai_content():
    messages = [
        HumanMessage(content="hola"),
        AIMessage(content="¿Cuál es el nombre del MCP?"),
    ]
    assert last_agent_message(messages) == "¿Cuál es el nombre del MCP?"


def test_pending_items_merges_missing_fields_and_clarifications():
    req = MCPRequirement(
        clarifications_needed=["Definir dataset y tabla"],
        tools=[ToolSpec(
            name="t", description="d", returns_type="str", returns_description="r",
        )],
        mcp_name="bq_tools",
        description="BigQuery reader",
    )
    pending = pending_items(req)
    assert any("confirm" in p.lower() for p in pending)
