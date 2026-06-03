"""Tests for RAG code-context retrieval."""
from context.index import load_index, search_index
from context.service import format_context_for_prompt, retrieve_context, search_knowledge


def test_load_index_includes_patterns():
    chunks = load_index()
    sources = {c.source for c in chunks}
    assert "patterns" in sources


def test_search_knowledge_finds_fastmcp():
    hits = search_knowledge("fastmcp tool decorator", limit=3)
    assert hits
    assert any("fastmcp" in h.content.lower() for h in hits)


def test_retrieve_context_microservice():
    hits = retrieve_context("microservice controller_factory natural language", limit=5)
    assert hits
    text = format_context_for_prompt(hits).lower()
    assert "microservice" in text or "controller" in text


def test_search_index_scores_relevant_higher():
    chunks = load_index()
    hits = search_index("postgres create_connection DATABASE_URL", chunks=chunks, limit=3)
    assert hits
    assert hits[0].score >= hits[-1].score
