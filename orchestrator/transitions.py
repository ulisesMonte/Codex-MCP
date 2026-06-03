"""Fixed lifecycle transition table — events mark phases, handlers advance the pipeline."""
from __future__ import annotations

from events.types import EventTypes

# Event types that move the industrial pipeline forward (not conversational).
LIFECYCLE_TRANSITIONS: dict[str, list[str]] = {
    EventTypes.USER_MESSAGE_RECEIVED: [
        EventTypes.REQUIREMENTS_STARTED,
        EventTypes.REQUIREMENT_UPDATED,
        EventTypes.REQUIREMENTS_COMPLETED,
        EventTypes.CLARIFICATION_NEEDED,
    ],
    EventTypes.REQUIREMENTS_COMPLETED: [
        EventTypes.SCOUT_STARTED,
        EventTypes.SCOUT_COMPLETED,
        EventTypes.SCOUT_VALIDATION_STARTED,
        EventTypes.SCOUT_VALIDATION_COMPLETED,
    ],
    EventTypes.SCOUT_VALIDATION_COMPLETED: [
        EventTypes.DESIGN_STARTED,
        EventTypes.DESIGN_COMPLETED,
        EventTypes.DESIGN_FAILED,
    ],
    EventTypes.DESIGN_COMPLETED: [
        EventTypes.CODE_GENERATION_STARTED,
        EventTypes.CODE_GENERATED,
        EventTypes.CODE_GENERATION_FAILED,
    ],
    EventTypes.CODE_GENERATED: [
        EventTypes.VALIDATION_STARTED,
        EventTypes.VALIDATION_PASSED,
        EventTypes.VALIDATION_FAILED,
        EventTypes.VALIDATION_RETRY_SCHEDULED,
    ],
    EventTypes.VALIDATION_RETRY_SCHEDULED: [
        EventTypes.CODE_REPAIR_STARTED,
        EventTypes.CODE_GENERATED,
    ],
    EventTypes.VALIDATION_PASSED: [
        EventTypes.DEPLOYMENT_STARTED,
        EventTypes.CODE_READY,
        EventTypes.MCP_DEPLOYED,
        EventTypes.DEPLOYMENT_FAILED,
    ],
    EventTypes.CODE_READY: [EventTypes.REGISTRY_UPDATE_STARTED, EventTypes.REGISTRY_UPDATED],
    EventTypes.MCP_DEPLOYED: [EventTypes.REGISTRY_UPDATE_STARTED, EventTypes.REGISTRY_UPDATED],
}

# Handlers subscribe to these trigger events (fixed flow — not LLM-chosen).
HANDLER_TRIGGERS: dict[str, str] = {
    "RequirementsHandler": EventTypes.USER_MESSAGE_RECEIVED,
    "ScoutPhaseHandler": EventTypes.REQUIREMENTS_COMPLETED,
    "DesignHandler": EventTypes.SCOUT_VALIDATION_COMPLETED,
    "CreatorHandler": EventTypes.DESIGN_COMPLETED,
    "CreatorRetryHandler": EventTypes.VALIDATION_RETRY_SCHEDULED,
    "ValidatorHandler": EventTypes.CODE_GENERATED,
    "DeployHandler": EventTypes.VALIDATION_PASSED,
    "RegistryHandler": EventTypes.CODE_READY,
    "RegistryDeployHandler": EventTypes.MCP_DEPLOYED,
}

SCOUT_PROFILES_ORDER = ("mcp", "api", "data", "docs")
