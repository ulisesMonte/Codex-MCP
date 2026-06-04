"""Tests for design and creator application services."""
from domain.codegen.design_builder import DeterministicDesignBuilder
from models.mcp_design import MCPDesign, ToolImplementation
from models.mcp_requirement import MCPRequirement, ToolSpec
from services.creator_service import CreatorService
from services.design_service import DesignService
from shared.parallel import AgentThreadPool


def _sample_req() -> MCPRequirement:
    return MCPRequirement(
        mcp_name="parallel_tools",
        description="MCP with multiple tools",
        tools=[
            ToolSpec(name=f"tool_{i}", description=f"Tool {i}", returns_type="str")
            for i in range(4)
        ],
    )


def test_design_builder_parallel_tools():
    builder = DeterministicDesignBuilder()
    design = builder.build(_sample_req())
    assert len(design.tools) == 4
    assert design.server_filename == "parallel_tools_server.py"


def test_creator_service_render_structure():
    req = MCPRequirement(
        mcp_name="test_mcp",
        description="Test",
        tools=[ToolSpec(name="run", description="Run", returns_type="str")],
    )
    design = MCPDesign(
        requirement=req,
        server_filename="test_mcp_server.py",
        imports=[],
        tools=[
            ToolImplementation(
                name="run",
                signature="",
                return_type="str",
                description="Run",
                returns_description="ok",
                body='    return "ok"',
            )
        ],
        resources=[],
    )
    service = CreatorService()
    code = service.render_code(design)
    assert service.has_fastmcp_structure(code)


def test_agent_thread_pool_runs_parallel():
    pool = AgentThreadPool(max_workers=2)
    results = pool.run_parallel(
        {
            "a": lambda: 1,
            "b": lambda: 2,
        }
    )
    assert results == {"a": 1, "b": 2}


def test_design_service_baseline_only_without_llm(monkeypatch):
    service = DesignService()

    def _skip_llm(*_args, **_kwargs):
        raise RuntimeError("LLM offline")

    monkeypatch.setattr(service, "_try_llm_design", _skip_llm)

    from domain.session import MCPFactorySession

    req = _sample_req()
    session = MCPFactorySession({"requirement": req, "phase": "designing"})
    result = service.create_design(session)
    assert result.design is not None
    assert result.baseline_only
