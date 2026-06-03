"""Scout loaded .md knowledge bases and generate research briefs."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from config.paths import (
    awesome_knowledge_dir,
    context_docs_dir,
    context_knowledge_dir,
    context_scouted_dir,
)
from context.repo_scout import _build_keywords
from models.mcp_requirement import MCPRequirement
from models.scout_report import ScoutedFile, ScoutedRepo, ScoutReport

_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```", re.M)
_HEADING_RE = re.compile(r"^#{1,3}\s+(.+)$", re.M)


def run_docs_scout(
    requirement: MCPRequirement,
    session_id: str,
    *,
    max_sources: int = 3,
) -> ScoutReport:
    """Pick relevant local .md files and generate a research brief .md."""
    keywords = _build_keywords(requirement, [
        "mcp", "fastmcp", "tool", "api", "python", "microservice",
        "database", "connection", "factory", "pattern",
    ])

    candidates = _collect_local_md_files()
    ranked = _rank_md_files(candidates, keywords)

    report = ScoutReport(
        profile="docs",
        agent_name="scout_docs_agent",
    )
    out_dir = context_scouted_dir() / session_id / "docs"
    out_dir.mkdir(parents=True, exist_ok=True)

    selected = ranked[:max_sources]
    excerpts: list[tuple[str, str, str]] = []

    for score, path, rel in selected:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            report.errors.append(f"{rel}: {exc}")
            continue
        if len(text.strip()) < 60:
            continue
        excerpt = _extract_useful_excerpt(text, keywords)
        excerpts.append((rel, str(path), excerpt))
        report.files.append(
            ScoutedFile(
                repo="local",
                path=rel,
                content=excerpt,
                local_path=str(path),
            )
        )
        report.repos.append(
            ScoutedRepo(
                slug=rel,
                reason=f"local md score={score}",
                files_fetched=1,
            )
        )

    brief = _generate_research_brief(requirement, session_id, excerpts, keywords)
    brief_path = out_dir / "research_brief.md"
    brief_path.write_text(brief, encoding="utf-8")

    report.files.append(
        ScoutedFile(
            repo="generated",
            path="research_brief.md",
            content=brief,
            local_path=str(brief_path),
        )
    )

    meta = {
        "session_id": session_id,
        "mcp_name": requirement.mcp_name,
        "sources": [e[0] for e in excerpts],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    if len(report.files) >= 2:
        report.status = "ok"
    elif len(report.files) >= 1:
        report.status = "partial"
    else:
        report.status = "failed"
        report.errors.append("No local .md sources found — run sync_tech_docs.py first")

    return report


def _collect_local_md_files() -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    knowledge = context_knowledge_dir()

    for path in knowledge.glob("*.md"):
        files.append((path, f"patterns/{path.name}"))

    docs_root = context_docs_dir()
    if docs_root.exists():
        for path in docs_root.rglob("*.md"):
            if path.name.startswith("_"):
                continue
            rel = f"docs/{path.relative_to(docs_root)}".replace("\\", "/")
            files.append((path, rel))

    # Skip awesome link indexes — only use if no docs synced (fallback excerpts)
    awesome = awesome_knowledge_dir()
    if awesome.exists() and len(files) < 5:
        for path in awesome.rglob("README.md"):
            if path.name.startswith("_"):
                continue
            list_name = path.parent.name
            rel = f"awesome/{list_name}/README.md"
            files.append((path, rel))

    return files


def _rank_md_files(
    candidates: list[tuple[Path, str]],
    keywords: list[str],
) -> list[tuple[int, Path, str]]:
    scored: list[tuple[int, Path, str]] = []
    for path, rel in candidates:
        lower = rel.lower()
        score = sum(2 for k in keywords if k in lower)
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:3000].lower()
            score += sum(1 for k in keywords if k in head)
        except OSError:
            continue
        if "awesome/" in lower:
            score = max(0, score - 3)
        if score > 0 or "patterns/" in lower or "docs/" in lower:
            scored.append((score, path, rel))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def _extract_useful_excerpt(text: str, keywords: list[str], max_len: int = 3500) -> str:
    blocks: list[str] = []
    for block in _CODE_BLOCK_RE.findall(text):
        if any(k in block.lower() for k in keywords) or "def " in block or "@mcp" in block:
            blocks.append(block.strip())
        if sum(len(b) for b in blocks) > max_len:
            break

    if blocks:
        excerpt = "\n\n".join(blocks[:4])
        return excerpt[:max_len]

    for heading in _HEADING_RE.finditer(text):
        start = heading.start()
        chunk = text[start : start + 1200]
        if any(k in chunk.lower() for k in keywords):
            blocks.append(chunk.strip())
        if len("\n\n".join(blocks)) > max_len:
            break

    if blocks:
        return "\n\n".join(blocks)[:max_len]

    return text[:max_len]


def _generate_research_brief(
    requirement: MCPRequirement,
    session_id: str,
    excerpts: list[tuple[str, str, str]],
    keywords: list[str],
) -> str:
    tool_lines = [
        f"- `{t.name}`: {t.description}"
        + (f" (hint: {t.implementation_hint})" if t.implementation_hint else "")
        for t in requirement.tools
    ]
    dep_lines = [f"- `{d}`" for d in requirement.dependencies]

    parts = [
        f"# Research brief — `{requirement.mcp_name}`",
        "",
        f"- Session: `{session_id}`",
        f"- Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- Keywords: {', '.join(keywords[:12])}",
        "",
        "## Requirement summary",
        "",
        requirement.description or "(no description)",
        "",
        "## Tools to implement",
        "",
        *(tool_lines or ["- (none yet)"]),
        "",
        "## Dependencies",
        "",
        *(dep_lines or ["- (none inferred)"]),
        "",
        "## Implementation guidance",
        "",
        "- Prefer real Python in tool bodies; use `os.getenv()` for secrets.",
        "- Factory tools must accept `specification: str` and return source code.",
        "- Follow FastMCP `@mcp.tool()` patterns from excerpts below.",
        "",
    ]

    if excerpts:
        parts.append("## Source excerpts (local knowledge base)\n")
        for rel, _, excerpt in excerpts:
            parts.append(f"### From `{rel}`\n")
            parts.append(excerpt)
            parts.append("")
    else:
        parts.append("_No local excerpts matched — sync tech docs with `python scripts/sync_tech_docs.py`._\n")

    return "\n".join(parts)
