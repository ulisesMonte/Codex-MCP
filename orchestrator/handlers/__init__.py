"""Pipeline event handlers — each stage reacts to a fixed trigger event."""
from __future__ import annotations

from orchestrator.handlers.creator import CreatorHandler, CreatorRetryHandler
from orchestrator.handlers.deploy import DeployHandler
from orchestrator.handlers.design import DesignHandler
from orchestrator.handlers.registry import RegistryDeployHandler, RegistryHandler
from orchestrator.handlers.requirements import RequirementsHandler
from orchestrator.handlers.scout_phase import ScoutPhaseHandler
from orchestrator.handlers.validator import ValidatorHandler

__all__ = [
    "RequirementsHandler",
    "ScoutPhaseHandler",
    "DesignHandler",
    "CreatorHandler",
    "CreatorRetryHandler",
    "ValidatorHandler",
    "DeployHandler",
    "RegistryHandler",
    "RegistryDeployHandler",
    "register_pipeline_handlers",
]


def register_pipeline_handlers(dispatcher) -> None:
    """Register all lifecycle handlers on the dispatcher."""
    for handler in (
        RequirementsHandler(),
        ScoutPhaseHandler(),
        DesignHandler(),
        CreatorHandler(),
        CreatorRetryHandler(),
        ValidatorHandler(),
        DeployHandler(),
        RegistryHandler(),
        RegistryDeployHandler(),
    ):
        dispatcher.register(handler)
