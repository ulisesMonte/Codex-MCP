"""Shared logic for parallel scout (relevador) agents."""
from __future__ import annotations

from typing import TYPE_CHECKING

from context.docs_scout import run_docs_scout
from context.repo_scout import SCOUT_PROFILES, run_scout
from shared.progress import agent_note
from events.types import EventTypes
from models.scout_report import ScoutReport
from orchestrator.events import publish_event

if TYPE_CHECKING:
    from orchestrator.state import MCPFactoryState


def scout_agent_node(state: "MCPFactoryState", profile: str) -> "MCPFactoryState":
    """LangGraph node: discover repos and fetch code files for one profile."""
    cfg = SCOUT_PROFILES[profile]
    agent_name = cfg["agent_name"]
    req = state.get("requirement")
    session_id = state.get("session_id", "default")

    if req is None:
        report = ScoutReport(
            profile=profile,
            agent_name=agent_name,
            status="failed",
            errors=["No requirement in state"],
        )
        return {"scout_reports": [report.model_dump()]}

    agent_note(f"Scout [{profile}] — relevando repos y código…")
    publish_event(
        state,
        EventTypes.SCOUT_STARTED,
        agent_name,
        f"Scout started ({profile})",
        payload={"profile": profile},
    )

    report = run_scout(profile, req, session_id)

    agent_note(
        f"Scout [{profile}] listo: {report.file_count} archivos ({report.status})"
    )
    publish_event(
        state,
        EventTypes.SCOUT_COMPLETED,
        agent_name,
        f"Scout completed ({profile})",
        payload={
            "profile": profile,
            "status": report.status,
            "files": report.file_count,
            "repos": [r.slug for r in report.repos],
        },
    )
    return {"scout_reports": [report.model_dump()]}


def scout_docs_agent_node(state: "MCPFactoryState") -> "MCPFactoryState":
    """LangGraph node: survey local .md knowledge and generate research brief."""
    agent_name = "scout_docs_agent"
    req = state.get("requirement")
    session_id = state.get("session_id", "default")

    if req is None:
        report = ScoutReport(
            profile="docs",
            agent_name=agent_name,
            status="failed",
            errors=["No requirement in state"],
        )
        return {"scout_reports": [report.model_dump()]}

    agent_note("Scout [docs] — relevando .md locales y generando brief…")
    publish_event(
        state,
        EventTypes.SCOUT_STARTED,
        agent_name,
        "Docs scout started",
        payload={"profile": "docs"},
    )

    report = run_docs_scout(req, session_id)

    agent_note(f"Scout [docs] listo: {report.file_count} md ({report.status})")
    publish_event(
        state,
        EventTypes.SCOUT_COMPLETED,
        agent_name,
        "Docs scout completed",
        payload={
            "profile": "docs",
            "status": report.status,
            "files": report.file_count,
            "generated": any(f.repo == "generated" for f in report.files),
        },
    )
    return {"scout_reports": [report.model_dump()]}
