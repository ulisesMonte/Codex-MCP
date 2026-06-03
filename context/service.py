"""High-level context API — Option C hybrid RAG."""
from __future__ import annotations

from context.index import CODEGEN_SOURCES, load_codegen_index, load_index, search_index
from context.models import ContextChunk


def retrieve_context(query: str, *, limit: int = 5, codegen_only: bool = False) -> list[ContextChunk]:
    return search_index(query, limit=limit, codegen_only=codegen_only)


def retrieve_codegen_context(
    query: str,
    *,
    dependencies: list[str] | None = None,
    limit: int = 8,
) -> list[ContextChunk]:
    """
    RAG for Design/Creator agents: patterns + synced docs + generated MCPs + templates.
    Excludes awesome link indexes (use discovery separately for deps/names).
    """
    enriched = query
    if dependencies:
        enriched += " " + " ".join(dependencies)

    chunks = search_index(enriched, limit=limit * 2, codegen_only=True)

    # Boost chunks whose title/tags match declared pip dependencies
    if dependencies:
        deps_lower = {d.lower().replace("_", "-") for d in dependencies}
        boosted: list[ContextChunk] = []
        for c in chunks:
            score = c.score
            title_lower = c.title.lower()
            for dep in deps_lower:
                base = dep.split("[")[0]
                if base in title_lower or base.replace("-", "") in title_lower.replace("-", ""):
                    score += 5
            boosted.append(ContextChunk(c.source, c.title, c.content, score))
        chunks = sorted(boosted, key=lambda x: x.score, reverse=True)

    return chunks[:limit]


def search_discovery(query: str, limit: int = 3) -> list[ContextChunk]:
    chunks = load_index()
    discovery = [c for c in chunks if c.source == "discovery"]
    return search_index(query, chunks=discovery, limit=limit)


def search_knowledge(query: str, limit: int = 3) -> list[ContextChunk]:
    chunks = load_index()
    corpus = [c for c in chunks if c.source in {"patterns", "docs"}]
    return search_index(query, chunks=corpus, limit=limit)


def search_generated_mcps(query: str, limit: int = 3) -> list[ContextChunk]:
    chunks = load_codegen_index()
    generated = [c for c in chunks if c.source == "generated"]
    return search_index(query, chunks=generated, limit=limit)


def get_similar_implementation(
    mcp_name: str,
    tool_names: list[str],
    limit: int = 5,
) -> list[ContextChunk]:
    terms = " ".join([mcp_name, *tool_names, "fastmcp", "tool"])
    return retrieve_codegen_context(terms, limit=limit)


def format_context_for_prompt(chunks: list[ContextChunk]) -> str:
    if not chunks:
        return ""
    parts = [
        "## Retrieved technical context (patterns + docs + examples — prefer over generic links)\n"
    ]
    for chunk in chunks:
        parts.append(chunk.format())
        parts.append("")
    return "\n".join(parts).strip()


def format_discovery_for_prompt(chunks: list[ContextChunk]) -> str:
    if not chunks:
        return ""
    parts = ["## Ecosystem hints (package/repo names only — not implementation)\n"]
    for chunk in chunks:
        parts.append(chunk.format())
    return "\n".join(parts).strip()
