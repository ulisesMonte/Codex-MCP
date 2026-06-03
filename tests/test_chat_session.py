from rich.console import Console

from cli.chat_session import GatheringChatUI
from events.view import EventLogView
from models.mcp_requirement import MCPRequirement
from orchestrator.state import MCPFactoryState


def test_chat_build_has_chat_and_events_columns():
    chat = GatheringChatUI(console=Console(width=120), event_view=EventLogView())
    chat.add_user("Quiero un MCP de BigQuery")
    layout = chat.build()
    assert layout["chat"] is not None
    assert layout["events"] is not None


def test_apply_state_adds_agent_and_missing():
    chat = GatheringChatUI(console=Console(width=120), event_view=EventLogView())
    state: MCPFactoryState = {
        "session_id": "s",
        "messages": [],
        "requirement": MCPRequirement(
            mcp_name="",
            description="",
            clarifications_needed=["Definir dataset"],
        ),
        "agent_prompt": "¿Cómo se llama el MCP?",
        "phase": "gathering",
    }
    chat.apply_state_after_turn(state)
    roles = [line.role for line in chat.lines]
    assert "agent" in roles
    assert "system" in roles
    assert any("Definir dataset" in line.body for line in chat.lines)


def test_append_thinking_keeps_rolling_log():
    chat = GatheringChatUI(console=Console(width=120), event_view=EventLogView())
    chat.append_thinking("Scout [mcp] started")
    chat.append_thinking("Scout [api] started")
    assert "Scout [mcp]" in chat.thinking
    assert "Scout [api]" in chat.thinking

