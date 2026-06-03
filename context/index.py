"""Build and search a weighted code-knowledge index (Option C hybrid RAG)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from config.paths import (
    context_discovery_dir,
    context_docs_dir,
    context_knowledge_dir,
    generated_mcps_dir,
    get_project_root,
    registry_path,
    validated_knowledge_dir,
)
from context.models import ContextChunk

_TOKEN_RE = re.compile(r"[a-z0-9_]{3,}")

# Codegen agents use these sources (real patterns + docs + our code + validated feedback).
CODEGEN_SOURCES = frozenset({"patterns", "docs", "generated", "template", "validated"})

# Awesome / discovery: ecosystem map only — low weight, not for tool bodies.
DISCOVERY_SOURCES = frozenset({"discovery"})

SOURCE_WEIGHT: dict[str, float] = {
    "validated": 3.5,
    "docs": 3.0,
    "patterns": 3.0,
    "generated": 2.5,
    "template": 2.0,
    "registry": 1.0,
    "discovery": 0.2,
}

_TEXT_EXTENSIONS = {".md", ".py", ".rst", ".txt"}


def load_index() -> list[ContextChunk]:
    chunks: list[ContextChunk] = []
    chunks.extend(_load_patterns())
    chunks.extend(_load_docs())
    chunks.extend(_load_validated())
    chunks.extend(_load_generated_mcps())
    chunks.extend(_load_templates())
    chunks.extend(_load_registry())
    chunks.extend(_load_discovery())
    return chunks


def load_codegen_index() -> list[ContextChunk]:
    """Index for Design/Creator agents — excludes awesome link indexes."""
    return [c for c in load_index() if c.source in CODEGEN_SOURCES]


def search_index(
    query: str,
    chunks: list[ContextChunk] | None = None,
    limit: int = 5,
    *,
    codegen_only: bool = False,
) -> list[ContextChunk]:
    corpus = chunks if chunks is not None else load_index()
    if codegen_only:
        corpus = [c for c in corpus if c.source in CODEGEN_SOURCES]

    tokens = _tokenize(query)
    if not tokens:
        return corpus[:limit]

    scored: list[ContextChunk] = []
    for chunk in corpus:
        hay = _tokenize(f"{chunk.title} {chunk.content} {chunk.source}")
        overlap = sum(1 for t in tokens if t in hay)
        bonus = sum(2 for t in tokens if t in chunk.title.lower())
        weight = SOURCE_WEIGHT.get(chunk.source, 1.0)
        score = (overlap + bonus) * weight
        if score > 0:
            scored.append(ContextChunk(chunk.source, chunk.title, chunk.content, score))

    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:limit]


def _load_patterns() -> list[ContextChunk]:
    """Internal pattern files (context/knowledge/*.md only — not awesome/)."""
    chunks: list[ContextChunk] = []
    knowledge_dir = context_knowledge_dir()
    if not knowledge_dir.exists():
        return chunks
    for path in sorted(knowledge_dir.glob("*.md")):
        chunks.append(_chunk_from_file(path, "patterns", path.stem))
    return chunks


def _load_docs() -> list[ContextChunk]:
    """Synced technical docs and code samples (context/docs/)."""
    chunks: list[ContextChunk] = []
    docs_dir = context_docs_dir()
    if not docs_dir.exists():
        return chunks
    for path in sorted(docs_dir.rglob("*")):
        if not path.is_file() or path.name.startswith("_"):
            continue
        if path.suffix.lower() not in _TEXT_EXTENSIONS:
            continue
        try:
            rel = str(path.relative_to(docs_dir)).replace("\\", "/")
        except ValueError:
            rel = path.name
        chunks.append(_chunk_from_file(path, "docs", rel, max_len=14_000))
    return chunks


def _load_validated() -> list[ContextChunk]:
    """Past validated scout research (context/knowledge/validated/)."""
    chunks: list[ContextChunk] = []
    validated_dir = validated_knowledge_dir()
    if not validated_dir.exists():
        return chunks
    for path in sorted(validated_dir.rglob("research.md")):
        if path.name.startswith("_"):
            continue
        try:
            rel = str(path.relative_to(validated_dir)).replace("\\", "/")
        except ValueError:
            rel = path.name
        chunks.append(_chunk_from_file(path, "validated", rel, max_len=14_000))
    return chunks


def _load_discovery() -> list[ContextChunk]:
    """Awesome-derived ecosystem index (discovery-only)."""
    chunks: list[ContextChunk] = []
    disc_dir = context_discovery_dir()
    eco_path = disc_dir / "ecosystem.json"
    if not eco_path.exists():
        return chunks
    try:
        data = json.loads(eco_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return chunks
    summary = json.dumps(
        {
            "pypi_packages": data.get("pypi_packages", [])[:100],
            "github_repos_sample": data.get("github_repos", [])[:50],
            "stats": data.get("stats", {}),
        },
        indent=2,
    )
    chunks.append(
        ContextChunk(
            source="discovery",
            title="ecosystem.json",
            content=summary,
        )
    )
    return chunks


def _chunk_from_file(
    path: Path,
    source: str,
    title: str,
    max_len: int = 12_000,
) -> ContextChunk:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        content = ""
    if len(content) > max_len:
        content = content[:max_len] + "\n\n... truncated ..."
    return ContextChunk(source=source, title=title, content=content)


def _load_generated_mcps() -> list[ContextChunk]:
    chunks: list[ContextChunk] = []
    gen_dir = generated_mcps_dir()
    if not gen_dir.exists():
        return chunks
    for path in sorted(gen_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > 6000:
            text = text[:6000] + "\n# ... truncated ..."
        chunks.append(
            ContextChunk(source="generated", title=path.name, content=text)
        )
    return chunks


def _load_templates() -> list[ContextChunk]:
    chunks: list[ContextChunk] = []
    templates_dir = get_project_root() / "templates"
    if not templates_dir.exists():
        return chunks
    for path in sorted(templates_dir.glob("*.j2")):
        chunks.append(
            ContextChunk(
                source="template",
                title=path.name,
                content=path.read_text(encoding="utf-8"),
            )
        )
    return chunks


def _load_registry() -> list[ContextChunk]:
    chunks: list[ContextChunk] = []
    reg_path = registry_path()
    if not reg_path.exists():
        return chunks
    try:
        data = json.loads(reg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return chunks
    entries = data if isinstance(data, list) else data.get("mcps", [])
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or entry.get("mcp_name") or "unknown"
        summary = json.dumps(entry, indent=2, ensure_ascii=False)
        chunks.append(ContextChunk(source="registry", title=str(name), content=summary))
    return chunks


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))
