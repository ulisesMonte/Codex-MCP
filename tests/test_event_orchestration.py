"""Tests for event-driven pipeline orchestration."""
import sys
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from events import EventTypes, JsonlEventStore, reset_event_bus
from events.runtime import get_event_bus
from models.mcp_design import GeneratedMCP, MCPDesign, ToolImplementation
from models.mcp_requirement import MCPRequirement, ToolSpec
from models.scout_report import ValidatedResearch
from orchestrator.coordinator import get_coordinator, reset_coordinator
from orchestrator.events import publish_event
from orchestrator.session_state import get_session_state_store


def _req() -> MCPRequirement:
    return MCPRequirement(
        mcp_name="test_mcp",
        description="Test MCP",
        tools=[
            ToolSpec(
                name="do_thing",
                description="Does a thing",
                returns_type="str",
                returns_description="result",
            )
        ],
        is_complete=True,
    )


def _design(req: MCPRequirement) -> MCPDesign:
    return MCPDesign(
        server_filename="test_mcp_server.py",
        requirement=req,
        imports=["from fastmcp import FastMCP"],
        tools=[
            ToolImplementation(
                name="do_thing",
                signature="",
                return_type="str",
                description="Does a thing",
                returns_description="result",
                body="return 'ok'",
            )
        ],
    )


def test_dispatcher_runs_full_pipeline_with_mocks(tmp_path, monkeypatch):
    monkeypatch.setenv("ORCHESTRATION_MODE", "events")
    session_id = "evt-session-1"
    reset_event_bus(session_id)
    reset_coordinator(session_id)

    store = JsonlEventStore(tmp_path)
    bus = get_event_bus(session_id, store=store)

    req = _req()
    design = _design(req)
    generated = GeneratedMCP(
        design=design,
        code="from fastmcp import FastMCP\nmcp = FastMCP('x')\n",
        server_path="/tmp/test_mcp_server.py",
        validation_passed=True,
        status="generated",
    )
    validated = ValidatedResearch(
        is_valid=True,
        total_files=5,
        total_repos=2,
        context_markdown="# research",
    )

    def requirements_side(state):
        publish_event(state, EventTypes.REQUIREMENTS_STARTED, "requirements_agent", "start")
        publish_event(state, EventTypes.REQUIREMENTS_COMPLETED, "requirements_agent", "done")
        return {"requirement": req, "phase": "complete", "messages": state.get("messages", [])}

    def scout_side(state):
        publish_event(
            state,
            EventTypes.SCOUT_COMPLETED,
            "scout",
            "ok",
            payload={"profile": "mcp"},
        )
        return {"scout_reports": [{"profile": "mcp", "agent_name": "scout_mcp_agent", "status": "ok", "files": []}]}

    def validator_side(state):
        publish_event(state, EventTypes.SCOUT_VALIDATION_STARTED, "scout_validator_agent", "start")
        publish_event(state, EventTypes.SCOUT_VALIDATION_COMPLETED, "scout_validator_agent", "done")
        return {"validated_research": validated.model_dump(), "phase": "designing"}

    def design_side(state):
        publish_event(state, EventTypes.DESIGN_STARTED, "mcp_design_agent", "start")
        publish_event(state, EventTypes.DESIGN_COMPLETED, "mcp_design_agent", "done")
        return {"design": design}

    def creator_side(state):
        publish_event(state, EventTypes.CODE_GENERATION_STARTED, "mcp_creator_agent", "start")
        publish_event(state, EventTypes.CODE_GENERATED, "mcp_creator_agent", "done")
        return {"generated_mcp": generated}

    def validate_side(state):
        publish_event(state, EventTypes.VALIDATION_STARTED, "validator_agent", "start")
        publish_event(state, EventTypes.VALIDATION_PASSED, "validator_agent", "passed")
        return {"generated_mcp": generated, "validation_attempts": 1}

    def deploy_side(state):
        publish_event(state, EventTypes.DEPLOYMENT_STARTED, "deployer", "start")
        publish_event(state, EventTypes.CODE_READY, "deployer", "ready")
        return {"phase": "done", "generated_mcp": generated}

    def registry_side(state):
        publish_event(state, EventTypes.REGISTRY_UPDATE_STARTED, "registry", "start")
        publish_event(state, EventTypes.REGISTRY_UPDATED, "registry", "done")
        return {"phase": "done"}

    with patch("orchestrator.handlers.requirements.requirements_agent_node", side_effect=requirements_side), patch(
        "orchestrator.handlers.scout_phase.scout_mcp_agent_node", side_effect=scout_side
    ), patch("orchestrator.handlers.scout_phase.scout_api_agent_node", side_effect=scout_side), patch(
        "orchestrator.handlers.scout_phase.scout_data_agent_node", side_effect=scout_side
    ), patch(
        "orchestrator.handlers.scout_phase.scout_docs_agent_node", side_effect=scout_side
    ), patch(
        "orchestrator.handlers.scout_phase.scout_validator_agent_node", side_effect=validator_side
    ), patch(
        "orchestrator.handlers.design.mcp_design_agent_node", side_effect=design_side
    ), patch(
        "orchestrator.handlers.creator.mcp_creator_agent_node", side_effect=creator_side
    ), patch(
        "orchestrator.handlers.validator.validator_agent_node", side_effect=validate_side
    ), patch("orchestrator.handlers.deploy.deployer_node", side_effect=deploy_side), patch(
        "orchestrator.handlers.registry.registry_updater_node", side_effect=registry_side
    ):
        coord = get_coordinator(session_id, bus)
        result = coord.run_user_turn(
            {"session_id": session_id, "messages": [], "phase": "gathering", "validation_attempts": 0}
        )

    assert result.get("phase") == "done"
    types = [e.type for e in store.read_session(session_id)]
    assert EventTypes.USER_MESSAGE_RECEIVED in types
    assert EventTypes.REQUIREMENTS_COMPLETED in types
    assert EventTypes.SCOUT_VALIDATION_COMPLETED in types
    assert EventTypes.DESIGN_COMPLETED in types
    assert EventTypes.CODE_GENERATED in types
    assert EventTypes.VALIDATION_PASSED in types
    assert EventTypes.CODE_READY in types
    assert EventTypes.REGISTRY_UPDATED in types
    reset_coordinator(session_id)
    reset_event_bus(session_id)


def test_transition_table_documents_scout_phase():
    from orchestrator.transitions import HANDLER_TRIGGERS, LIFECYCLE_TRANSITIONS

    assert EventTypes.REQUIREMENTS_COMPLETED in LIFECYCLE_TRANSITIONS
    assert EventTypes.SCOUT_VALIDATION_COMPLETED in LIFECYCLE_TRANSITIONS[
        EventTypes.REQUIREMENTS_COMPLETED
    ]
    assert HANDLER_TRIGGERS["ScoutPhaseHandler"] == EventTypes.REQUIREMENTS_COMPLETED
