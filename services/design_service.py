"""Orchestrates MCP design: deterministic baseline + optional LLM merge."""
from __future__ import annotations

from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage

from context.service import (
    format_context_for_prompt,
    get_similar_implementation,
    retrieve_codegen_context,
)
from domain.codegen.design_builder import DeterministicDesignBuilder
from domain.design.llm_design_parser import LlmDesignParser
from domain.session import MCPFactorySession
from llm.json_parse import extract_json_dict
from llm.ollama_client import get_coder_llm
from models.mcp_design import MCPDesign
from models.mcp_requirement import MCPRequirement
from shared.parallel import AgentThreadPool
from shared.progress import agent_note

SYSTEM_PROMPT = """You are an expert Python FastMCP developer.
Given an MCP requirement, output JSON with real tool implementations.

{
  "server_filename": "name_server.py",
  "imports": ["import os"],
  "tools": [{
    "name": "tool_name",
    "signature": "param: str",
    "return_type": "str",
    "description": "...",
    "returns_description": "...",
    "body": "    x = param.upper()\\n    return x"
  }],
  "resources": [],
  "has_external_calls": false,
  "estimated_complexity": "simple"
}

RULES:
- body: real Python, 4-space indent, use \\n between lines
- NEVER TODO, stub, "Not implemented", or return f"Executed ..."
- Use os.getenv() for secrets; never hardcode credentials
- Factory tools: specification: str → return complete generated source code
- BigQuery: google.cloud.bigquery + GOOGLE_APPLICATION_CREDENTIALS
- DB tools: use DATABASE_URL env var
"""


@dataclass
class DesignContext:
    """RAG + scout research gathered for design."""

    rag_block: str
    scout_block: str

    @property
    def combined(self) -> str:
        if self.scout_block and self.rag_block:
            return f"{self.scout_block}\n\n{self.rag_block}"
        return self.scout_block or self.rag_block


@dataclass
class DesignResult:
    """Output of the design phase."""

    design: MCPDesign
    llm_used: bool
    baseline_only: bool


class DesignService:
    """Application service: requirement + research → MCPDesign."""

    def __init__(
        self,
        builder: DeterministicDesignBuilder | None = None,
        parser: LlmDesignParser | None = None,
        pool: AgentThreadPool | None = None,
    ) -> None:
        self.builder = builder or DeterministicDesignBuilder()
        self.parser = parser or LlmDesignParser(self.builder)
        self.pool = pool or AgentThreadPool()

    def create_design(self, session: MCPFactorySession) -> DesignResult:
        req = session.requirement
        if req is None:
            raise ValueError("No requirement in session")

        parallel = self.pool.run_parallel(
            {
                "baseline": lambda: self.builder.build(req),
                "context": lambda: self._load_context(req, session),
            }
        )
        baseline: MCPDesign = parallel["baseline"]
        context: DesignContext = parallel["context"]

        design = baseline
        llm_used = False

        try:
            llm_design = self._try_llm_design(req, context)
            if llm_design is not None:
                design = self.builder.merge(baseline, llm_design)
                llm_used = True
        except Exception as e:
            agent_note(f"LLM design skipped — usando baseline determinístico: {e}")

        return DesignResult(
            design=design,
            llm_used=llm_used,
            baseline_only=not llm_used,
        )

    def _load_context(self, req: MCPRequirement, session: MCPFactorySession) -> DesignContext:
        query = f"{req.mcp_name} {' '.join(t.name for t in req.tools)} {req.description}"

        rag_results = self.pool.run_parallel(
            {
                "primary": lambda: retrieve_codegen_context(
                    query, dependencies=req.dependencies, limit=8
                ),
                "similar": lambda: get_similar_implementation(
                    req.mcp_name, [t.name for t in req.tools], limit=5
                ),
            }
        )
        rag_chunks = rag_results["primary"] or rag_results["similar"]
        rag_block = format_context_for_prompt(rag_chunks)

        validated = session.validated_research()
        scout_block = validated.context_markdown if validated else ""
        if not scout_block:
            raw = session.raw().get("validated_research") or {}
            scout_block = raw.get("context_markdown", "") if isinstance(raw, dict) else ""

        return DesignContext(rag_block=rag_block, scout_block=scout_block)

    def _try_llm_design(self, req: MCPRequirement, context: DesignContext) -> MCPDesign | None:
        llm = get_coder_llm(temperature=0.05, quiet=True)

        hints = []
        for t in req.tools:
            if t.implementation_hint:
                hints.append(f"- {t.name}: {t.implementation_hint}")
        hint_block = "\n".join(hints)

        prompt = f"Design MCP server:\n\n{req.model_dump_json(indent=2)}\n\n"
        if hint_block:
            prompt += f"Implementation hints (mandatory):\n{hint_block}\n\n"
        if context.combined:
            prompt += f"{context.combined}\n\n"
        prompt += "JSON only. Real implementations — no stubs."

        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        data = extract_json_dict(response.content.strip())
        return self.parser.parse(req, data)
