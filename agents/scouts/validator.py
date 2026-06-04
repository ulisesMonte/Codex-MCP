"""Validates 4 scout agents and persists feedback .md sections."""
from __future__ import annotations

from typing import TYPE_CHECKING

from domain.research.scout_validator import ScoutResearchValidator, validate_reports
from shared.progress import agent_note
from context.feedback_store import persist_validated_research
from events.types import EventTypes
from models.scout_report import ScoutReport, ValidatedResearch
from orchestrator.events import publish_event

if TYPE_CHECKING:
    from orchestrator.state import MCPFactoryState

_scout_validator = ScoutResearchValidator()


def scout_validator_agent_node(state: "MCPFactoryState") -> "MCPFactoryState":
    agent_note("Scout validator — fusionando investigación…")

    publish_event(
        state,
        EventTypes.SCOUT_VALIDATION_STARTED,
        "scout_validator_agent",
        "Validating scout reports",
    )

    raw_reports = state.get("scout_reports") or []
    reports = [ScoutReport.model_validate(r) if isinstance(r, dict) else r for r in raw_reports]
    reports = _scout_validator.dedupe_by_profile(reports)

    validated = _scout_validator.validate(reports)

    persisted: list[str] = []
    req = state.get("requirement")
    session_id = state.get("session_id", "default")
    if validated.is_valid and req is not None:
        persisted = persist_validated_research(req, session_id, reports, validated)
        validated.persisted_paths = persisted
        validated.feedback_sections = sorted(
            {r.profile for r in reports if r.status != "failed"}
        )
        agent_note(f"Feedback guardado: {len(persisted)} archivos en validated/")

    level = "info" if validated.is_valid else "warning"
    publish_event(
        state,
        EventTypes.SCOUT_VALIDATION_COMPLETED,
        "scout_validator_agent",
        "Scout validation completed",
        level=level,
        payload={
            "is_valid": validated.is_valid,
            "total_files": validated.total_files,
            "total_repos": validated.total_repos,
            "persisted": len(persisted),
            "warnings": validated.warnings,
        },
    )

    if validated.is_valid:
        agent_note(
            f"Relevamiento OK: {validated.total_files} files / {validated.total_repos} repos"
        )
    else:
        agent_note(
            f"Relevamiento parcial: {validated.total_files} files — continuando"
        )

    return {
        "validated_research": validated.model_dump(),
        "phase": "designing",
    }


def _dedupe_by_profile(reports: list[ScoutReport]) -> list[ScoutReport]:
    return _scout_validator.dedupe_by_profile(reports)


def _validate_reports(reports: list[ScoutReport]) -> ValidatedResearch:
    return validate_reports(reports)
