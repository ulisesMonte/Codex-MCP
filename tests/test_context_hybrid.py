"""Tests for Option C hybrid RAG."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from context.index import CODEGEN_SOURCES, load_codegen_index, load_index, search_index
from context.service import retrieve_codegen_context, search_knowledge
from scripts.build_discovery_index import extract_from_markdown


def test_load_index_has_patterns_not_awesome_bulk():
    chunks = load_index()
    sources = {c.source for c in chunks}
    assert "patterns" in sources
    # Awesome markdown should NOT be indexed as patterns/docs
    awesome_titles = [c.title for c in chunks if "awesome-nodejs" in c.title.lower()]
    assert not awesome_titles


def test_codegen_index_excludes_discovery():
    all_chunks = load_index()
    codegen = load_codegen_index()
    assert all(c.source in CODEGEN_SOURCES for c in codegen)
    discovery_count = sum(1 for c in all_chunks if c.source == "discovery")
    assert discovery_count <= 1  # only ecosystem.json summary


def test_search_knowledge_finds_fastmcp():
    hits = search_knowledge("fastmcp tool decorator", limit=3)
    assert hits
    assert any("fastmcp" in h.content.lower() for h in hits)


def test_retrieve_codegen_context_prefers_patterns():
    hits = retrieve_codegen_context("microservice controller_factory specification", limit=5)
    assert hits
    assert hits[0].source in CODEGEN_SOURCES


def test_extract_from_markdown_finds_pypi():
    text = "[httpx](https://pypi.org/project/httpx/) and [repo](https://github.com/encode/httpx)"
    parsed = extract_from_markdown(text)
    assert "httpx" in parsed["pypi_packages"]
    assert "encode/httpx" in parsed["github_repos"]
