"""Validates 4 scout agents and persists feedback .md sections."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from cli.agent_console import agent_note
from context.feedback_store import persist_validated_research
from events.types import EventTypes
from models.scout_report import ScoutReport, ValidatedResearch
from orchestrator.events import publish_event

if TYPE_CHECKING:
    from orchestrator.state import MCPFactoryState

_PLACEHOLDER_RE = re.compile(
    r"generated successfully|not implemented|stub|todo: implement",
    re.I,
)

_AWESOME_PROFILES = frozenset({"mcp", "api", "data"})


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
    reports = _dedupe_by_profile(reports)

    validated = _validate_reports(reports)

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
    by_profile: dict[str, ScoutReport] = {}
    for report in reports:
        by_profile[report.profile] = report
    return list(by_profile.values())


def _validate_reports(reports: list[ScoutReport]) -> ValidatedResearch:
    warnings: list[str] = []
    rejected: list[str] = []
    summaries: list[str] = []
    accepted_files: list[tuple[str, str, str, str]] = []  # repo, path, content, profile

    by_profile = {r.profile: r for r in reports}
    ok_scouts = sum(1 for r in reports if r.status == "ok")
    partial_scouts = sum(1 for r in reports if r.status == "partial")

    if len(reports) < 4:
        warnings.append(f"Expected 4 scout reports (mcp/api/data/docs), got {len(reports)}")

    for report in reports:
        summaries.append(
            f"- **{report.agent_name}** ({report.profile}): "
            f"{report.file_count} files, status={report.status}"
        )
        if report.errors:
            warnings.extend(f"{report.agent_name}: {e}" for e in report.errors[:2])

        min_files = 1 if report.profile == "docs" else 2
        useful = 0
        for f in report.files:
            if report.profile != "docs" and _PLACEHOLDER_RE.search(f.content[:500]):
                rejected.append(f"{f.repo}:{f.path} (placeholder content)")
                continue
            if len(f.content.strip()) < 60:
                rejected.append(f"{f.repo}:{f.path} (too short)")
                continue
            accepted_files.append((f.repo, f.path, f.content, report.profile))
            useful += 1

        if useful < min_files:
            warnings.append(
                f"{report.agent_name}: only {useful} useful files (expected >= {min_files})"
            )

    docs_report = by_profile.get("docs")
    has_generated_brief = bool(
        docs_report and any(f.repo == "generated" for f in docs_report.files)
    )
    if docs_report and not has_generated_brief:
        warnings.append("docs scout: missing generated research_brief.md")

    awesome_files = [f for f in accepted_files if f[3] in _AWESOME_PROFILES]
    total_files = len(accepted_files)
    repos = {r for r, _, _, p in accepted_files if p in _AWESOME_PROFILES and r not in ("local", "generated")}

    is_valid = (
        total_files >= 5
        and ok_scouts >= 2
        and has_generated_brief
        and len(awesome_files) >= 3
    )
    if not is_valid and total_files >= 3 and has_generated_brief and (ok_scouts + partial_scouts) >= 3:
        is_valid = True
        warnings.append("Accepted with partial scout coverage")

    markdown = _build_context_markdown(summaries, accepted_files, warnings)

    return ValidatedResearch(
        is_valid=is_valid,
        total_files=total_files,
        total_repos=len(repos),
        context_markdown=markdown,
        scout_summaries=summaries,
        warnings=warnings,
        rejected_files=rejected,
    )


def _build_context_markdown(
    summaries: list[str],
    files: list[tuple[str, str, str, str]],
    warnings: list[str],
) -> str:
    parts = [
        "## Validated research from scout agents (use for implementation)\n",
        "### Scout summary\n",
        *summaries,
        "",
    ]
    if warnings:
        parts.append("### Warnings\n")
        parts.extend(f"- {w}" for w in warnings[:5])
        parts.append("")

    generated = [f for f in files if f[0] == "generated"]
    local = [f for f in files if f[0] == "local"]
    github = [f for f in files if f[0] not in ("generated", "local")]

    if generated:
        parts.append("### Generated research brief\n")
        for _, path, content, _ in generated:
            parts.append(f"#### `{path}`\n")
            parts.append(f"```markdown\n{content[:5000]}\n```\n")

    if local:
        parts.append("### Local knowledge excerpts\n")
        for _, path, content, _ in local[:4]:
            parts.append(f"#### `{path}`\n")
            parts.append(f"```\n{content[:3000]}\n```\n")

    if github:
        parts.append("### Fetched from GitHub (awesome → repos)\n")
        for repo, path, content, _ in github[:10]:
            parts.append(f"#### `{repo}` — `{path}`\n")
            parts.append(f"```\n{content[:3500]}\n```\n")

    return "\n".join(parts)
