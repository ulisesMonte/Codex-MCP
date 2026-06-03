"""Persist validated scout research for RAG feedback loops."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from config.paths import validated_knowledge_dir
from models.mcp_requirement import MCPRequirement
from models.scout_report import ScoutReport, ValidatedResearch

_SECTIONS = ("mcp", "api", "data", "docs", "combined")


def persist_validated_research(
    requirement: MCPRequirement,
    session_id: str,
    reports: list[ScoutReport],
    validated: ValidatedResearch,
) -> list[str]:
    """
    Write validated .md sections under context/knowledge/validated/.
    Returns list of written file paths.
    """
    if not validated.is_valid:
        return []

    base = validated_knowledge_dir()
    base.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_mcp = _safe_slug(requirement.mcp_name or "unnamed_mcp")
    run_id = f"{safe_mcp}_{stamp}"

    for report in reports:
        if report.status == "failed":
            continue
        section = report.profile if report.profile in _SECTIONS else "combined"
        section_dir = base / section / run_id
        section_dir.mkdir(parents=True, exist_ok=True)

        section_md = _build_section_markdown(requirement, session_id, report)
        md_path = section_dir / "research.md"
        md_path.write_text(section_md, encoding="utf-8")
        written.append(str(md_path))

        meta = {
            "section": section,
            "profile": report.profile,
            "agent": report.agent_name,
            "session_id": session_id,
            "mcp_name": requirement.mcp_name,
            "status": report.status,
            "files": report.file_count,
            "persisted_at": datetime.now(timezone.utc).isoformat(),
        }
        (section_dir / "_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        written.append(str(section_dir / "_meta.json"))

        sources_dir = section_dir / "sources"
        sources_dir.mkdir(exist_ok=True)
        for i, f in enumerate(report.files[:5]):
            safe = _safe_slug(f.path.replace("/", "_"))[:60]
            src_path = sources_dir / f"{i}_{safe}.md"
            src_path.write_text(
                f"# Source: {f.repo}/{f.path}\n\n{f.content}",
                encoding="utf-8",
            )
            written.append(str(src_path))

    combined_dir = base / "combined" / run_id
    combined_dir.mkdir(parents=True, exist_ok=True)
    combined_path = combined_dir / "research.md"
    combined_path.write_text(validated.context_markdown, encoding="utf-8")
    written.append(str(combined_path))

    combined_meta = {
        "session_id": session_id,
        "mcp_name": requirement.mcp_name,
        "total_files": validated.total_files,
        "total_repos": validated.total_repos,
        "sections": [r.profile for r in reports if r.status != "failed"],
        "persisted_at": datetime.now(timezone.utc).isoformat(),
    }
    (combined_dir / "_meta.json").write_text(json.dumps(combined_meta, indent=2), encoding="utf-8")
    written.append(str(combined_dir / "_meta.json"))

    _update_index(base, run_id, requirement.mcp_name, session_id, reports)
    return written


def _build_section_markdown(
    requirement: MCPRequirement,
    session_id: str,
    report: ScoutReport,
) -> str:
    lines = [
        f"# Validated research — {report.profile}",
        "",
        f"- MCP: `{requirement.mcp_name}`",
        f"- Session: `{session_id}`",
        f"- Agent: `{report.agent_name}`",
        f"- Status: {report.status}",
        "",
    ]
    if report.repos:
        lines.append("## Sources\n")
        for repo in report.repos:
            lines.append(f"- `{repo.slug}` — {repo.reason}")
        lines.append("")

    lines.append("## Content\n")
    for f in report.files:
        lines.append(f"### `{f.repo}/{f.path}`\n")
        lines.append(f"```\n{f.content[:5000]}\n```\n")
    return "\n".join(lines)


def _update_index(
    base: Path,
    run_id: str,
    mcp_name: str,
    session_id: str,
    reports: list[ScoutReport],
) -> None:
    index_path = base / "index.json"
    index: list[dict] = []
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            index = []

    index.append({
        "run_id": run_id,
        "mcp_name": mcp_name,
        "session_id": session_id,
        "sections": sorted({r.profile for r in reports if r.status != "failed"}),
        "combined_path": f"combined/{run_id}/research.md",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    index = index[-200:]
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")
    return slug[:48] or "unnamed"
