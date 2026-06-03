"""Smoke tests for agent modules that publish lifecycle events."""
import importlib


def test_mcp_design_agent_imports_event_types():
    mod = importlib.import_module("agents.mcp_design_agent")
    from events.types import EventTypes

    assert mod.EventTypes is EventTypes
