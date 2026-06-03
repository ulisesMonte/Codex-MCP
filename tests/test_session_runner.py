from rich.console import Console

from cli.session_runner import MCPCreateSessionRunner, new_session_id


def test_new_session_id_has_expected_prefix():
    assert new_session_id().startswith("mcp-factory-")


def test_initial_state_contains_session_id():
    runner = MCPCreateSessionRunner(
        console=Console(),
        graph_factory=lambda: None,
        check_ollama=lambda: True,
    )

    state = runner._initial_state("session-123")

    assert state["session_id"] == "session-123"
    assert state["phase"] == "gathering"
    assert state["validation_attempts"] == 0
    assert state.get("agent_prompt") is None
