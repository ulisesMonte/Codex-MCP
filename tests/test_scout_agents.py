"""Tests for scout validator and repo ranking."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents.scout_validator_agent import _validate_reports
from context.docs_scout import run_docs_scout
from context.feedback_store import persist_validated_research
from context.repo_scout import _rank_repos, _score_slug
from models.mcp_requirement import MCPRequirement, ToolSpec
from models.scout_report import ScoutReport, ScoutedFile, ScoutedRepo


def _docs_report() -> ScoutReport:
    return ScoutReport(
        profile="docs",
        agent_name="scout_docs_agent",
        status="ok",
        repos=[ScoutedRepo(slug="patterns/fastmcp.md", reason="local", files_fetched=1)],
        files=[
            ScoutedFile(
                repo="local",
                path="patterns/fastmcp.md",
                content="@mcp.tool()\ndef example(): return 1\n" * 10,
            ),
            ScoutedFile(
                repo="generated",
                path="research_brief.md",
                content="# Research brief\n\nImplementation guidance " * 15,
            ),
        ],
    )


def test_score_slug_keywords():
    assert _score_slug("encode/httpx", ["httpx", "api"]) >= 2


def test_rank_repos_includes_dependency_hint():
    req = MCPRequirement(
        mcp_name="bq_tool",
        description="bigquery query tool",
        tools=[ToolSpec(name="query", description="d", returns_type="str", returns_description="r")],
        dependencies=["google-cloud-bigquery"],
    )
    ranked = _rank_repos(["bigquery", "query"], req)
    assert any("python-bigquery" in s for s in ranked)


def test_validator_accepts_four_scouts_with_files():
    reports = [
        ScoutReport(
            profile="mcp",
            agent_name="scout_mcp_agent",
            status="ok",
            repos=[ScoutedRepo(slug="jlowin/fastmcp", reason="test", files_fetched=2)],
            files=[
                ScoutedFile(repo="jlowin/fastmcp", path="README.md", content="FastMCP tool example " * 20),
                ScoutedFile(repo="jlowin/fastmcp", path="examples/x.py", content="def tool(): return 1\n" * 10),
            ],
        ),
        ScoutReport(
            profile="api",
            agent_name="scout_api_agent",
            status="ok",
            repos=[ScoutedRepo(slug="fastapi/fastapi", reason="test", files_fetched=2)],
            files=[
                ScoutedFile(repo="fastapi/fastapi", path="README.md", content="FastAPI routing " * 20),
                ScoutedFile(repo="fastapi/fastapi", path="main.py", content="@app.get('/')\ndef root(): pass\n" * 5),
            ],
        ),
        ScoutReport(
            profile="data",
            agent_name="scout_data_agent",
            status="partial",
            repos=[ScoutedRepo(slug="psycopg/psycopg", reason="test", files_fetched=1)],
            files=[
                ScoutedFile(repo="psycopg/psycopg", path="README.md", content="PostgreSQL connection " * 20),
            ],
        ),
        _docs_report(),
    ]
    result = _validate_reports(reports)
    assert result.is_valid
    assert result.total_files >= 5
    assert "Validated research" in result.context_markdown


def test_validator_rejects_placeholder_content():
    reports = [
        ScoutReport(
            profile="mcp",
            agent_name="scout_mcp_agent",
            files=[
                ScoutedFile(repo="x/y", path="a.py", content="return 'generated successfully'"),
            ],
        ),
        _docs_report(),
    ]
    result = _validate_reports(reports)
    assert result.total_files <= 2
    assert result.rejected_files


def test_docs_scout_generates_brief(tmp_path, monkeypatch):
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "fastmcp_patterns.md").write_text(
        "```python\n@mcp.tool()\ndef my_tool(): pass\n```\n",
        encoding="utf-8",
    )
    scouted = tmp_path / "scouted"
    monkeypatch.setenv("CONTEXT_KNOWLEDGE_DIR", str(knowledge))
    monkeypatch.setenv("CONTEXT_DOCS_DIR", str(tmp_path / "docs"))
    monkeypatch.setenv("CONTEXT_SCOUTED_DIR", str(scouted))

    req = MCPRequirement(
        mcp_name="test_mcp",
        description="FastMCP microservice factory",
        tools=[ToolSpec(name="build", description="build mcp", returns_type="str", returns_description="code")],
    )
    report = run_docs_scout(req, "sess1")
    assert any(f.repo == "generated" and f.path == "research_brief.md" for f in report.files)
    assert report.status in ("ok", "partial")


def test_persist_validated_research_creates_sections(tmp_path, monkeypatch):
    validated_dir = tmp_path / "validated"
    monkeypatch.setenv("VALIDATED_KNOWLEDGE_DIR", str(validated_dir))

    req = MCPRequirement(mcp_name="my_mcp", description="test")
    reports = [
        ScoutReport(
            profile="mcp",
            agent_name="scout_mcp_agent",
            status="ok",
            files=[ScoutedFile(repo="a/b", path="x.py", content="def f(): pass\n" * 5)],
        ),
        _docs_report(),
    ]
    validated = _validate_reports(reports)
    validated.is_valid = True

    paths = persist_validated_research(req, "sess1", reports, validated)
    assert paths
    assert (validated_dir / "mcp").exists()
    assert (validated_dir / "docs").exists()
    assert (validated_dir / "combined").exists()
    assert (validated_dir / "index.json").exists()
